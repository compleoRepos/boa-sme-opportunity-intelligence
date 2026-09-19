#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_command docker
load_local_env

POSTGRES_DB=${POSTGRES_DB:-boa_sme}
POSTGRES_ADMIN_USER=${POSTGRES_ADMIN_USER:-boa_admin}

expect_rejected() {
  local name=$1
  local pattern=$2
  local sql=$3
  local output
  output=$(mktemp)
  if compose exec -T postgres psql -v ON_ERROR_STOP=1 \
    --username "$POSTGRES_ADMIN_USER" --dbname "$POSTGRES_DB" \
    --command "$sql" >"$output" 2>&1; then
    cat "$output"
    rm -f "$output"
    echo "FAIL $name: PostgreSQL accepted a forbidden operation" >&2
    exit 1
  fi
  if ! grep -Eq "$pattern" "$output"; then
    cat "$output"
    rm -f "$output"
    echo "FAIL $name: unexpected rejection" >&2
    exit 1
  fi
  rm -f "$output"
  echo "PASS $name"
}

version=$(compose exec -T postgres psql --tuples-only --no-align \
  --username "$POSTGRES_ADMIN_USER" --dbname "$POSTGRES_DB" \
  --command "SELECT version_num FROM alembic_version;")
[[ "$version" == "0013_label_catalog" ]] || {
  echo "FAIL migration head: expected 0013_label_catalog, received $version" >&2
  exit 1
}
echo "PASS migration head"

expect_rejected "history UPDATE blocked" "append-only" \
  "UPDATE config.label_catalog_versions SET label='forbidden' WHERE version=1;"
expect_rejected "history DELETE blocked" "append-only" \
  "DELETE FROM config.label_catalog_versions WHERE version=1;"
expect_rejected "history TRUNCATE blocked" "append-only" \
  "TRUNCATE config.label_catalog_versions;"
expect_rejected "runtime code collision blocked" "duplicate key" \
  "INSERT INTO config.label_catalog (id,namespace,code,locale,label,current_version,active,updated_by,justification,created_by) SELECT gen_random_uuid(),'OTHER',code,locale,'Collision',1,true,'test','Collision interdite','test' FROM config.label_catalog WHERE code='OPEN';"

PYTHONPATH=backend/src:. pytest \
  tests/unit/test_label_catalog.py \
  tests/unit/test_gateway_labels.py \
  -q --disable-warnings

echo "Label catalog validation completed."
