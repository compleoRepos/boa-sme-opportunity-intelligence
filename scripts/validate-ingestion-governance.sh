#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/common.sh
source "$SCRIPT_DIR/common.sh"

require_command jq
load_local_env
: "${POSTGRES_ADMIN_PASSWORD:?POSTGRES_ADMIN_PASSWORD is required in infrastructure/.env}"

DATABASE=${INGESTION_TEST_DATABASE:-boa_ingestion_governance}
OUTPUT=${INGESTION_TEST_OUTPUT:-docs/evidence/ingestion/RESULTATS-INGESTION-GOUVERNEE.json}
RUNNER=boa-ingestion-governance-runner
SERVICE=boa-ingestion-governance-transaction
IMAGE=boa-sme-opportunity-intelligence-transaction
TEMP_ENV=$(mktemp)

cleanup() {
  local exit_code=$?
  trap - EXIT
  set +e
  docker_cli rm -f "$SERVICE" "$RUNNER" >/dev/null 2>&1
  compose exec -T postgres psql --set=ON_ERROR_STOP=1 \
    --username "${POSTGRES_ADMIN_USER:-boa_admin}" --dbname postgres \
    --set=database_name="$DATABASE" >/dev/null 2>&1 <<'SQL'
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = :'database_name' AND pid <> pg_backend_pid();
SELECT format('DROP DATABASE IF EXISTS %I', :'database_name') \gexec
SQL
  rm -f "$TEMP_ENV"
  exit "$exit_code"
}
trap cleanup EXIT

compose up -d postgres >/dev/null
wait_for_healthy postgres 180
compose build customer transaction >/dev/null

data_network=$(compose config --format json | jq -r '.networks.data.name')
app_network=$(compose config --format json | jq -r '.networks.app.name')
[[ -n "$data_network" && -n "$app_network" ]] || {
  echo "Unable to resolve Compose data/app networks" >&2
  exit 1
}

compose exec -T postgres psql --set=ON_ERROR_STOP=1 \
  --username "${POSTGRES_ADMIN_USER:-boa_admin}" --dbname postgres \
  --set=database_name="$DATABASE" >/dev/null <<'SQL'
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = :'database_name' AND pid <> pg_backend_pid();
SELECT format('DROP DATABASE IF EXISTS %I', :'database_name') \gexec
SELECT format('CREATE DATABASE %I', :'database_name') \gexec
SQL

admin_url="postgresql+psycopg://${POSTGRES_ADMIN_USER:-boa_admin}:${POSTGRES_ADMIN_PASSWORD}@postgres:5432/${DATABASE}"
compose run --rm --no-deps --entrypoint /bin/sh \
  --env "DATABASE_URL=$admin_url" \
  customer -ec 'cd /app/database && exec alembic -c alembic.ini upgrade head' >/dev/null

tested_source_files=(
  backend/src/boa_oi/ingestion.py
  backend/src/boa_oi/models/entities.py
  backend/src/boa_oi/transaction_api.py
  database/migrations/versions/0001_initial.py
  database/migrations/versions/0016_ingestion_governance.py
  scripts/migrate.sh
  scripts/validate-ingestion-governance.sh
  scripts/validate_ingestion_governance.py
)
tested_source_digest=$(
  for source_file in "${tested_source_files[@]}"; do
    source_hash=$(sha256sum "$PROJECT_ROOT/$source_file" | cut -d' ' -f1)
    printf '%s  %s\n' "$source_hash" "$source_file"
  done | sha256sum | cut -d' ' -f1
)
tested_source_csv=$(IFS=,; printf '%s' "${tested_source_files[*]}")
worktree_dirty=false
if [[ -n $(git status --porcelain -- "${tested_source_files[@]}") ]]; then
  worktree_dirty=true
fi

printf '%s\n' \
  "DATABASE_URL=$admin_url" \
  "INGESTION_DATABASE_URL=$admin_url" \
  "INGESTION_TRANSACTION_URL=http://ingestion-transaction:8080" \
  "INGESTION_GIT_COMMIT=$(git rev-parse HEAD)" \
  "INGESTION_WORKTREE_DIRTY=$worktree_dirty" \
  "INGESTION_TESTED_SOURCE_DIGEST=$tested_source_digest" \
  "INGESTION_TESTED_SOURCE_FILES=$tested_source_csv" \
  >"$TEMP_ENV"
chmod 600 "$TEMP_ENV"

docker_cli rm -f "$SERVICE" "$RUNNER" >/dev/null 2>&1 || true
docker_cli run -d --name "$SERVICE" --network "$data_network" \
  --env-file "$TEMP_ENV" \
  --env "APP_MODULE=boa_oi.api:app" \
  --env "SERVICE_NAME=transaction-service" \
  --env "BOA_AUTH_DISABLED=true" \
  --env "PORT=8080" \
  --cpus 0.50 --memory 384m \
  "$IMAGE" >/dev/null
docker_cli network connect --alias ingestion-transaction "$app_network" "$SERVICE"

docker_cli run -d --name "$RUNNER" --network "$data_network" \
  --env-file "$TEMP_ENV" \
  --mount "type=bind,src=$PROJECT_ROOT,dst=/workspace" \
  --workdir /workspace --entrypoint sh "$IMAGE" -c 'sleep infinity' >/dev/null
docker_cli network connect "$app_network" "$RUNNER"

echo "[ingestion] Validation PostgreSQL du contrat, de la quarantaine et de l'idempotence..."
docker_cli exec "$RUNNER" python scripts/validate_ingestion_governance.py \
  --output /tmp/boa-ingestion-governance-report.json \
  | tee /tmp/boa-ingestion-governance-run.json
mkdir -p "$PROJECT_ROOT/$(dirname "$OUTPUT")"
docker_cli cp "$RUNNER:/tmp/boa-ingestion-governance-report.json" "$PROJECT_ROOT/$OUTPUT"

status=$(jq -r '.status' "$PROJECT_ROOT/$OUTPUT")
[[ "$status" == PASS ]] || {
  echo "Ingestion governance validation status: $status" >&2
  exit 1
}
echo "[ingestion] PASS — preuve: $OUTPUT"
