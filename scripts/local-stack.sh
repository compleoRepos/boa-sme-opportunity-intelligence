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
PG_OS_USER=${PG_OS_USER:-claude}
PYTHON=${LOCAL_PYTHON:-$PROJECT_ROOT/../.venv-boa/bin/python}
AS_OF=${AS_OF_DATE:-2026-09-30}
CUSTOMER_COUNT=${PIPELINE_CUSTOMER_COUNT:-500}
BATCH=${PIPELINE_BATCH_SIZE:-50}
GATEWAY_PORT=${LOCAL_GATEWAY_PORT:-8080}
DATABASE_URL="postgresql+psycopg://$PGUSER:$PGPASSWORD_VALUE@127.0.0.1:$PGPORT/$PGDATABASE"

mkdir -p "$STATE_DIR/logs" "$STATE_DIR/pids"
if [[ $(id -u) -eq 0 ]]; then chown -R "$PG_OS_USER" "$STATE_DIR"; fi

# service -> port
declare -A PORTS=(
  [customer-service]=9001 [account-service]=9002 [transaction-service]=9003
  [mock-banking-api]=9004 [banking-integration-service]=9005 [analytics-service]=9006
  [signal-service]=9007 [opportunity-service]=9008 [product-service]=9009
  [action-service]=9010 [rule-management-service]=9011 [rule-engine-service]=9012
  [rule-simulation-service]=9013 [feature-store-service]=9014 [ml-engine-service]=9015
  [portfolio-service]=9016 [api-gateway]=$GATEWAY_PORT
)

url() { echo "http://127.0.0.1:${PORTS[$1]}"; }

pg_run() { runuser -u "$PG_OS_USER" -- "$@"; }

pg_up() {
  if [[ ! -d "$PGDATA" ]]; then
    mkdir -p "$PGDATA"; chown "$PG_OS_USER" "$PGDATA" "$STATE_DIR"
    pg_run "$PG_BIN/initdb" -D "$PGDATA" --username="$PGUSER" --auth=trust --encoding=UTF8 >/dev/null
    echo "port = $PGPORT" >> "$PGDATA/postgresql.conf"
    echo "listen_addresses = '127.0.0.1'" >> "$PGDATA/postgresql.conf"
    echo "unix_socket_directories = '$STATE_DIR'" >> "$PGDATA/postgresql.conf"
    echo "fsync = off" >> "$PGDATA/postgresql.conf"
    echo "synchronous_commit = off" >> "$PGDATA/postgresql.conf"
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
    export APP_ENV=local-demo LOG_LEVEL=WARNING PYTHONUNBUFFERED=1
    export CUSTOMER_SERVICE_URL="$(url customer-service)" ACCOUNT_SERVICE_URL="$(url account-service)"
    export TRANSACTION_SERVICE_URL="$(url transaction-service)" ANALYTICS_SERVICE_URL="$(url analytics-service)"
    export SIGNAL_SERVICE_URL="$(url signal-service)" OPPORTUNITY_SERVICE_URL="$(url opportunity-service)"
    export PRODUCT_SERVICE_URL="$(url product-service)" ACTION_SERVICE_URL="$(url action-service)"
    export BANKING_INTEGRATION_SERVICE_URL="$(url banking-integration-service)" MOCK_BANK_URL="$(url mock-banking-api)"
    export MOCK_BANKING_API_URL="$(url mock-banking-api)" BANKING_API_URL="$(url mock-banking-api)"
    export RULE_MANAGEMENT_SERVICE_URL="$(url rule-management-service)" RULE_ENGINE_SERVICE_URL="$(url rule-engine-service)"
    export RULE_SIMULATION_SERVICE_URL="$(url rule-simulation-service)" FEATURE_STORE_SERVICE_URL="$(url feature-store-service)"
    export ML_ENGINE_SERVICE_URL="$(url ml-engine-service)" PORTFOLIO_SERVICE_URL="$(url portfolio-service)"
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

post_json() {
  local target="$1" path="$2" payload="$3" key="$4"
  curl -fsS -X POST "$target$path" -H 'Content-Type: application/json' -H "X-Correlation-ID: local-$key" \
    -H "Idempotency-Key: local-$key" --data "$payload" -o /dev/null -w "%{http_code} $path\n"
}

pipeline() {
  local ids start end run
  run=${PIPELINE_RUN_ID:-$(date -u +%Y%m%dT%H%M%S)}
  for ((start=1; start<=CUSTOMER_COUNT; start+=BATCH)); do
    end=$((start + BATCH - 1)); [[ $end -le $CUSTOMER_COUNT ]] || end=$CUSTOMER_COUNT
    ids=$(seq -f 'SME-%05g' "$start" "$end" | jq -R . | jq -sc .)
    post_json "$(url analytics-service)" /internal/v1/analytics/recompute \
      "$(jq -nc --argjson ids "$ids" --arg asOf "$AS_OF" '{customerIds:$ids,asOf:$asOf,periods:["7D","30D","90D","180D","365D"]}')" "$run-an-$start"
    post_json "$(url signal-service)" /internal/v1/signals/evaluate \
      "$(jq -nc --argjson ids "$ids" --arg asOf "$AS_OF" '{customerIds:$ids,asOf:$asOf,periods:["90D"]}')" "$run-sig-$start"
    post_json "$(url opportunity-service)" /internal/v1/opportunities/generate \
      "$(jq -nc --argjson ids "$ids" --arg asOf "$AS_OF" '{customerIds:$ids,asOf:$asOf}')" "$run-opp-$start"
    post_json "$(url feature-store-service)" /internal/v1/features/materialize \
      "$(jq -nc --argjson ids "$ids" --arg asOf "$AS_OF" '{customerIds:$ids,asOf:$asOf}')" "$run-fs-$start"
    post_json "$(url ml-engine-service)" /internal/v1/ml/scores/batch \
      "$(jq -nc --argjson ids "$ids" --arg asOf "$AS_OF" '{customerIds:$ids,asOf:$asOf}')" "$run-ml-$start"
  done
  echo "Pipeline terminé (asOf=$AS_OF, $CUSTOMER_COUNT PME)."
}

seed_rules() {
  # Règles Rule Studio de démonstration (brouillons), créées via le Gateway avec la persona back-office.
  local persona='{"subject":"admin-01","username":"youssef.tazi","roles":["ADMIN","BUSINESS_ANALYST","RULE_APPROVER"],"branchIds":["ALL"]}'
  local existing
  existing=$(curl -fsS -H "X-Dev-Principal: $persona" "http://127.0.0.1:$GATEWAY_PORT/api/v1/rules?pageSize=100" | jq -r '.meta.totalCount // (.data | length)')
  if [[ "${existing:-0}" -gt 0 ]]; then echo "Rule Studio déjà initialisé ($existing règles)."; return; fi
  jq -c '.[]' "$PROJECT_ROOT/database/seed/rule-studio.json" | while read -r rule; do
    curl -fsS -X POST "http://127.0.0.1:$GATEWAY_PORT/api/v1/rules" -H 'Content-Type: application/json' \
      -H "X-Dev-Principal: $persona" -H "Idempotency-Key: seed-rule-$(echo "$rule" | jq -r .ruleId)" --data "$rule" -o /dev/null -w "%{http_code} rule $(echo "$rule" | jq -r .ruleId)\n"
  done
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
