#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"
require_command docker
require_command python3
failed=0
for script in "$PROJECT_ROOT"/scripts/*.sh "$PROJECT_ROOT"/infrastructure/docker/*.sh "$PROJECT_ROOT"/infrastructure/keycloak/*.sh "$PROJECT_ROOT"/infrastructure/postgres/*.sh; do
  [[ -e "$script" ]] || continue
  if ! bash -n "$script"; then failed=1; fi
done
python3 -m json.tool "$PROJECT_ROOT/infrastructure/keycloak/realm.json" >/dev/null
compose config --quiet
mapfile -t actual_services < <(compose config --services | sort)
required_services=(postgres keycloak frontend api-gateway customer account transaction banking-integration mock-bank analytics signal opportunity product action rule-management rule-engine rule-simulation)
for service in "${required_services[@]}"; do
  if ! printf '%s\n' "${actual_services[@]}" | grep -Fxq "$service"; then
    echo "Compose service missing: $service" >&2
    failed=1
  fi
done
if command -v shellcheck >/dev/null 2>&1; then
  shellcheck -x -P "$PROJECT_ROOT/scripts" "$PROJECT_ROOT"/scripts/*.sh "$PROJECT_ROOT"/infrastructure/docker/*.sh "$PROJECT_ROOT"/infrastructure/keycloak/*.sh "$PROJECT_ROOT"/infrastructure/postgres/*.sh
else
  echo "shellcheck not installed; bash -n validation completed" >&2
fi
if [[ $failed -ne 0 ]]; then
  echo "Infrastructure validation failed." >&2
  exit 1
fi
echo "Compose, Keycloak JSON and script syntax are valid."
