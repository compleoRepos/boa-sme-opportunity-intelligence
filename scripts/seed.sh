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
compose --profile tools run --rm demo-data-generator
