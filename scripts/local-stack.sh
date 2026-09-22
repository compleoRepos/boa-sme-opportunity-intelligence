#!/usr/bin/env bash
# Stack locale sans Docker : PostgreSQL natif + 16 services uvicorn + pipeline complet.
# Usage :
#   scripts/local-stack.sh up        # initdb, migrations, seed, services, pipeline (idempotent)
#   scripts/local-stack.sh services  # (re)démarre uniquement les services
#   scripts/local-stack.sh pipeline  # relance analytics -> signaux -> opportunités -> features -> ML
#   scripts/local-stack.sh down      # arrête services et PostgreSQL
#
# Mode démonstration uniquement : BOA_AUTH_DISABLED=true (aucun Keycloak), données synthétiques.
set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd)
STATE_DIR=${LOCAL_STACK_DIR:-$PROJECT_ROOT/.local-stack}
PGDATA=$STATE_DIR/pgdata
PGPORT=${LOCAL_PGPORT:-55432}
PGUSER=${LOCAL_PGUSER:-boa_admin}
PGPASSWORD_VALUE=${LOCAL_PGPASSWORD:-local-only}
PGDATABASE=${LOCAL_PGDATABASE:-boa_sme}
PG_BIN=${PG_BIN:-/usr/lib/postgresql/16/bin}
if [[ -z ${PG_OS_USER:-} ]]; then
  if [[ $(id -u) -eq 0 ]]; then PG_OS_USER=postgres; else PG_OS_USER=$(id -un); fi
fi
PYTHON=${LOCAL_PYTHON:-}
if [[ -z "$PYTHON" ]]; then
  if [[ -x "$PROJECT_ROOT/../.venv-boa/bin/python" ]]; then
    PYTHON="$PROJECT_ROOT/../.venv-boa/bin/python"
  else
    PYTHON=$(command -v python3)
  fi
fi
AS_OF=${AS_OF_DATE:-2026-09-30}
CUSTOMER_COUNT=${PIPELINE_CUSTOMER_COUNT:-500}
BATCH=${PIPELINE_BATCH_SIZE:-50}
GATEWAY_PORT=${LOCAL_GATEWAY_PORT:-8080}
DATABASE_URL="postgresql+psycopg://$PGUSER:$PGPASSWORD_VALUE@127.0.0.1:$PGPORT/$PGDATABASE"
export PYTHONPATH="$PROJECT_ROOT/backend/src:$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"

mkdir -p "$STATE_DIR/logs" "$STATE_DIR/pids"
if [[ $(id -u) -eq 0 ]]; then chown -R "$PG_OS_USER" "$STATE_DIR"; fi

# service -> port
declare -A PORTS=(
  [customer-service]=9001 [account-service]=9002 [transaction-service]=9003
  [mock-banking-api]=9004 [banking-integration-service]=9005 [analytics-service]=9006
  [signal-service]=9007 [opportunity-service]=9008 [product-service]=9009
  [action-service]=9010 [rule-management-service]=9011 [rule-engine-service]=9012
  [rule-simulation-service]=9013 [feature-store-service]=9014 [ml-engine-service]=9015
  [portfolio-service]=9016 [notification-service]=9017 [api-gateway]=$GATEWAY_PORT
)

url() { echo "http://127.0.0.1:${PORTS[$1]}"; }

pg_run() {
  if [[ $(id -un) == "$PG_OS_USER" ]]; then
    "$@"
  elif [[ $(id -u) -eq 0 ]]; then
    runuser -u "$PG_OS_USER" -- "$@"
  else
    sudo -n -u "$PG_OS_USER" -- "$@"
  fi
}

pg_up() {
  if [[ ! -d "$PGDATA" ]]; then
    mkdir -p "$PGDATA"; chown "$PG_OS_USER" "$PGDATA" "$STATE_DIR"
    pg_run "$PG_BIN/initdb" -D "$PGDATA" --username="$PGUSER" --auth=trust --encoding=UTF8 >/dev/null
    {
      echo "port = $PGPORT"
      echo "listen_addresses = '127.0.0.1'"
      echo "unix_socket_directories = '$STATE_DIR'"
      echo "fsync = off"
      echo "synchronous_commit = off"
    } >> "$PGDATA/postgresql.conf"
  fi
  if ! pg_run "$PG_BIN/pg_ctl" -D "$PGDATA" status >/dev/null 2>&1; then
    pg_run "$PG_BIN/pg_ctl" -D "$PGDATA" -l "$STATE_DIR/logs/postgres.log" -w start >/dev/null
  fi
  pg_run "$PG_BIN/psql" -h 127.0.0.1 -p "$PGPORT" -U "$PGUSER" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$PGDATABASE'" | grep -q 1 \
    || pg_run "$PG_BIN/createdb" -h 127.0.0.1 -p "$PGPORT" -U "$PGUSER" "$PGDATABASE"
  pg_run "$PG_BIN/psql" -h 127.0.0.1 -p "$PGPORT" -U "$PGUSER" -d postgres -qc "ALTER ROLE $PGUSER PASSWORD '$PGPASSWORD_VALUE'"
}

migrate() {
  # Comme scripts/migrate.sh : ces schémas sont provisionnés hors Alembic.
  for schema in rule feature_store ml portfolio; do
    pg_run "$PG_BIN/psql" -h 127.0.0.1 -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -qc "CREATE SCHEMA IF NOT EXISTS $schema"
  done
  (cd "$PROJECT_ROOT/database" && DATABASE_URL="$DATABASE_URL" "$PYTHON" -m alembic -c alembic.ini upgrade head)
}

seed() {
  local existing
  existing=$(pg_run "$PG_BIN/psql" -h 127.0.0.1 -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -tAc "SELECT count(*) FROM customer.customers" 2>/dev/null || echo 0)
  if [[ "${existing:-0}" -ge "$CUSTOMER_COUNT" ]]; then echo "Seed déjà présent ($existing PME)."; return; fi
  echo "Seed déterministe en cours (500 PME, 12 mois)…"
  (cd "$PROJECT_ROOT" && "$PYTHON" -m database.seed.generate --database-url "$DATABASE_URL")
}

start_service() {
  local name="$1" port="${PORTS[$1]}" pid_file="$STATE_DIR/pids/$1.pid"
  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then return; fi
  (
    cd "$PROJECT_ROOT/backend"
    export SERVICE_NAME="$name" PORT="$port" HOST=127.0.0.1 DATABASE_URL="$DATABASE_URL"
    export BOA_AUTH_DISABLED=true OIDC_ISSUER_URL=http://localhost/realms/local OIDC_AUDIENCE=boa-sme-api
    export APP_ENV=local LOG_LEVEL=WARNING PYTHONUNBUFFERED=1
    CUSTOMER_SERVICE_URL="$(url customer-service)"
    ACCOUNT_SERVICE_URL="$(url account-service)"
    TRANSACTION_SERVICE_URL="$(url transaction-service)"
    ANALYTICS_SERVICE_URL="$(url analytics-service)"
    SIGNAL_SERVICE_URL="$(url signal-service)"
    OPPORTUNITY_SERVICE_URL="$(url opportunity-service)"
    PRODUCT_SERVICE_URL="$(url product-service)"
    ACTION_SERVICE_URL="$(url action-service)"
    BANKING_INTEGRATION_SERVICE_URL="$(url banking-integration-service)"
    MOCK_BANK_URL="$(url mock-banking-api)"
    MOCK_BANKING_API_URL="$(url mock-banking-api)"
    BANKING_API_URL="$(url mock-banking-api)"
    RULE_MANAGEMENT_SERVICE_URL="$(url rule-management-service)"
    RULE_ENGINE_SERVICE_URL="$(url rule-engine-service)"
    RULE_SIMULATION_SERVICE_URL="$(url rule-simulation-service)"
    FEATURE_STORE_SERVICE_URL="$(url feature-store-service)"
    ML_ENGINE_SERVICE_URL="$(url ml-engine-service)"
    PORTFOLIO_SERVICE_URL="$(url portfolio-service)"
    NOTIFICATION_SERVICE_URL="$(url notification-service)"
    NOTIFICATION_SCOPE_SIGNING_SECRET=local-native-notification-signing-secret
    export CUSTOMER_SERVICE_URL ACCOUNT_SERVICE_URL TRANSACTION_SERVICE_URL
    export ANALYTICS_SERVICE_URL SIGNAL_SERVICE_URL OPPORTUNITY_SERVICE_URL
    export PRODUCT_SERVICE_URL ACTION_SERVICE_URL BANKING_INTEGRATION_SERVICE_URL
    export MOCK_BANK_URL MOCK_BANKING_API_URL BANKING_API_URL
    export RULE_MANAGEMENT_SERVICE_URL RULE_ENGINE_SERVICE_URL
    export RULE_SIMULATION_SERVICE_URL FEATURE_STORE_SERVICE_URL
    export ML_ENGINE_SERVICE_URL PORTFOLIO_SERVICE_URL NOTIFICATION_SERVICE_URL
    export NOTIFICATION_SCOPE_SIGNING_SECRET
    nohup "$PYTHON" -m uvicorn boa_oi.api:app --host 127.0.0.1 --port "$port" --log-level warning \
      >"$STATE_DIR/logs/$name.log" 2>&1 &
    echo $! >"$pid_file"
  )
}

wait_health() {
  local name="$1" tries=60
  until curl -fsS "$(url "$name")/health" >/dev/null 2>&1; do
    tries=$((tries - 1)); [[ $tries -gt 0 ]] || { echo "Service $name ne répond pas"; tail -20 "$STATE_DIR/logs/$name.log"; return 1; }
    sleep 0.5
  done
}

services_up() {
  for name in "${!PORTS[@]}"; do start_service "$name"; done
  for name in "${!PORTS[@]}"; do wait_health "$name"; done
  echo "Services démarrés. Gateway : http://127.0.0.1:$GATEWAY_PORT"
}

pipeline() {
  local run output source_revision source_branch code_digest code_tree
  run=${PIPELINE_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}
  output=${PIPELINE_EVIDENCE_FILE:-$STATE_DIR/pipeline-results.json}
  source_revision=$(git -C "$PROJECT_ROOT" rev-parse HEAD 2>/dev/null || echo UNKNOWN)
  source_branch=$(git -C "$PROJECT_ROOT" branch --show-current 2>/dev/null || echo UNKNOWN)
  if [[ -z $(git -C "$PROJECT_ROOT" status --porcelain -- backend database frontend/src infrastructure scripts tests .github/workflows) ]]; then
    code_tree=CLEAN
  else
    code_tree=DIRTY
  fi
  code_digest=$(
    cd "$PROJECT_ROOT"
    git ls-files -z --cached --others --exclude-standard backend database frontend/src infrastructure scripts tests .github/workflows \
      | sort -z | xargs -0 sha256sum | sha256sum | awk '{print $1}'
  )
  "$PYTHON" "$PROJECT_ROOT/scripts/run_pipeline_benchmark.py" \
    --customer-count "$CUSTOMER_COUNT" \
    --batch-size "$BATCH" \
    --as-of "$AS_OF" \
    --run-id "$run" \
    --analytics-url "$(url analytics-service)" \
    --signal-url "$(url signal-service)" \
    --opportunity-url "$(url opportunity-service)" \
    --feature-store-url "$(url feature-store-service)" \
    --ml-engine-url "$(url ml-engine-service)" \
    --source LOCAL_NATIVE_NO_DOCKER \
    --source-revision "$source_revision" \
    --source-branch "$source_branch" \
    --code-digest "$code_digest" \
    --code-tree "$code_tree" \
    --output "$output"
  printf 'Preuve pipeline : %s\n' "$output"
}

seed_rules() {
  # Chaque règle est vérifiée par ruleId puis créée uniquement si elle manque.
  (cd "$PROJECT_ROOT" && "$PYTHON" -m database.seed.rule_studio \
    --rules-url "http://127.0.0.1:$GATEWAY_PORT/api/v1/rules")
}

down() {
  for pid_file in "$STATE_DIR"/pids/*.pid; do
    [[ -f "$pid_file" ]] || continue
    kill "$(cat "$pid_file")" 2>/dev/null || true; rm -f "$pid_file"
  done
  pg_run "$PG_BIN/pg_ctl" -D "$PGDATA" -m fast stop >/dev/null 2>&1 || true
  echo "Stack locale arrêtée."
}

case "${1:-up}" in
  up) pg_up; migrate; seed; services_up; pipeline; seed_rules ;;
  services) pg_up; services_up ;;
  pipeline) pipeline ;;
  rules) seed_rules ;;
  down) down ;;
  *) echo "Commande inconnue : $1" >&2; exit 1 ;;
esac
