#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd)
COMPOSE_FILE=${COMPOSE_FILE:-$PROJECT_ROOT/infrastructure/docker-compose.yml}
ENV_FILE=${ENV_FILE:-$PROJECT_ROOT/infrastructure/.env}

docker_cli() {
  if [[ -S /var/run/docker.sock && ! -w /var/run/docker.sock ]] && command -v sudo >/dev/null; then
    sudo -n docker "$@"
  else
    docker "$@"
  fi
}

compose() {
  local args=(--file "$COMPOSE_FILE")
  if [[ -f "$ENV_FILE" ]]; then
    args+=(--env-file "$ENV_FILE")
  fi
  docker_cli compose "${args[@]}" "$@"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || { echo "Required command not found: $1" >&2; return 1; }
}

load_local_env() {
  if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
  fi
}

wait_for_healthy() {
  local service="$1" timeout_seconds="${2:-180}" start now container status
  start=$(date +%s)
  container=$(compose ps -q "$service")
  [[ -n "$container" ]] || { echo "No container found for $service" >&2; return 1; }
  while true; do
    status=$(docker_cli inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container")
    if [[ "$status" == healthy || "$status" == running ]]; then return 0; fi
    if [[ "$status" == unhealthy || "$status" == exited || "$status" == dead ]]; then
      compose logs --no-color "$service" >&2 || true
      return 1
    fi
    now=$(date +%s)
    if (( now - start >= timeout_seconds )); then
      echo "Timed out waiting for $service (last status: $status)" >&2
      compose logs --no-color "$service" >&2 || true
      return 1
    fi
    sleep 3
  done
}
