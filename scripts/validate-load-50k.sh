#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/common.sh
source "$SCRIPT_DIR/common.sh"

require_command jq
require_command openssl
load_local_env
: "${POSTGRES_ADMIN_PASSWORD:?POSTGRES_ADMIN_PASSWORD is required in infrastructure/.env}"

DATABASE=${LOAD_TEST_DATABASE:-boa_load_50k}
CUSTOMERS=${LOAD_TEST_CUSTOMERS:-50000}
OUTPUT=${LOAD_TEST_OUTPUT:-docs/evidence/load/RESULTATS-CHARGE-50000.json}
KEEP_DATABASE=${LOAD_TEST_KEEP_DATABASE:-false}
IMAGE=${LOAD_TEST_IMAGE:-boa-sme-opportunity-intelligence-customer}
RUNNER=boa-load-50k-runner
CUSTOMER=boa-load-50k-customer
OPPORTUNITY=boa-load-50k-opportunity
PORTFOLIO=boa-load-50k-portfolio
TEMP_ENV=$(mktemp)

cleanup() {
  local exit_code=$?
  trap - EXIT
  set +e
  docker_cli rm -f "$CUSTOMER" "$OPPORTUNITY" "$PORTFOLIO" >/dev/null 2>&1
  if [[ "$KEEP_DATABASE" != true ]]; then
    compose exec -T postgres psql --set=ON_ERROR_STOP=1 \
      --username "${POSTGRES_ADMIN_USER:-boa_admin}" --dbname postgres \
      --set=database_name="$DATABASE" >/dev/null 2>&1 <<'SQL'
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = :'database_name' AND pid <> pg_backend_pid();
SELECT format('DROP DATABASE IF EXISTS %I', :'database_name') \gexec
SQL
  fi
  docker_cli rm -f "$RUNNER" >/dev/null 2>&1
  rm -f "$TEMP_ENV"
  exit "$exit_code"
}
trap cleanup EXIT

compose up -d postgres >/dev/null
wait_for_healthy postgres 180
compose build customer >/dev/null

data_network=$(compose config --format json | jq -r '.networks.data.name')
app_network=$(compose config --format json | jq -r '.networks.app.name')
[[ -n "$data_network" && -n "$app_network" ]] || { echo "Unable to resolve Compose data/app networks" >&2; exit 1; }

load_git_commit=$(git rev-parse HEAD)
printf '%s\n' \
  "LOAD_ADMIN_DATABASE_URL=postgresql+psycopg://boa_admin:${POSTGRES_ADMIN_PASSWORD}@postgres:5432/${DATABASE}" \
  "LOAD_GIT_COMMIT=${load_git_commit}" \
  "LOAD_CUSTOMER_URL=http://load-customer:8080" \
  "LOAD_OPPORTUNITY_URL=http://load-opportunity:8080" \
  "LOAD_PORTFOLIO_URL=http://load-portfolio:8080" \
  >"$TEMP_ENV"
chmod 600 "$TEMP_ENV"

docker_cli rm -f "$CUSTOMER" "$OPPORTUNITY" "$PORTFOLIO" "$RUNNER" >/dev/null 2>&1 || true
docker_cli run -d --name "$RUNNER" --network "$data_network" \
  --env-file "$TEMP_ENV" \
  --mount "type=bind,src=$PROJECT_ROOT,dst=/workspace" \
  --workdir /workspace --entrypoint sh "$IMAGE" -c 'sleep infinity' >/dev/null
docker_cli network connect "$app_network" "$RUNNER"

echo "[load-50k] Préparation de ${CUSTOMERS} PME synthétiques dans une base isolée..."
docker_cli exec "$RUNNER" python scripts/load_test_50k.py prepare \
  --database "$DATABASE" --customers "$CUSTOMERS" | tee /tmp/boa-load-50k-prepare.json

start_service() {
  local name="$1" alias="$2" service="$3" cpus="$4" memory="$5"
  docker_cli run -d --name "$name" --network "$data_network" \
    --env-file "$TEMP_ENV" \
    --env "DATABASE_URL=postgresql+psycopg://boa_admin:${POSTGRES_ADMIN_PASSWORD}@postgres:5432/${DATABASE}" \
    --env "APP_MODULE=boa_oi.api:app" \
    --env "SERVICE_NAME=$service" \
    --env "BOA_AUTH_DISABLED=true" \
    --env "PORT=8080" \
    --cpus "$cpus" --memory "$memory" \
    "$IMAGE" >/dev/null
  docker_cli network connect --alias "$alias" "$app_network" "$name"
}

start_service "$CUSTOMER" load-customer customer-service 0.35 320m
start_service "$OPPORTUNITY" load-opportunity opportunity-service 0.75 512m
start_service "$PORTFOLIO" load-portfolio portfolio-service 0.35 320m

echo "[load-50k] Mesures HTTP concurrentes et plans PostgreSQL..."
docker_cli exec "$RUNNER" python scripts/load_test_50k.py run \
  --database "$DATABASE" --output /tmp/boa-load-50k-report.json \
  | tee /tmp/boa-load-50k-run.json
mkdir -p "$PROJECT_ROOT/$(dirname "$OUTPUT")"
docker_cli cp "$RUNNER:/tmp/boa-load-50k-report.json" "$PROJECT_ROOT/$OUTPUT"

status=$(jq -r '.status' "$PROJECT_ROOT/$OUTPUT")
[[ "$status" == PASS ]] || { echo "Load test status: $status" >&2; exit 1; }

echo "[load-50k] PASS — preuve: $OUTPUT"
