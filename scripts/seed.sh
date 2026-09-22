#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_command docker
load_local_env
compose up --detach postgres
wait_for_healthy postgres 120
"$SCRIPT_DIR/migrate.sh"
compose --profile tools run --rm --build demo-data-generator
compose up --detach keycloak rule-management
wait_for_healthy keycloak 300
wait_for_healthy rule-management 180
compose --profile tools run --rm --no-deps --build --entrypoint python demo-data-generator \
  -m database.seed.rule_studio \
  --rules-url http://rule-management:8080/internal/v1/rules
