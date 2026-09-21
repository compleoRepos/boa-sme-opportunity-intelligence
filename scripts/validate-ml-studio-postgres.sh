#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAME="${ML_STUDIO_POSTGRES_CONTAINER:-boa-ml-studio-pg-$$}"
PORT="${ML_STUDIO_POSTGRES_PORT:-55439}"
IMAGE="${ML_STUDIO_POSTGRES_IMAGE:-postgres:16.15-alpine}"
URL="postgresql+psycopg://postgres:postgres@127.0.0.1:${PORT}/boa_ml_studio"

if docker info >/dev/null 2>&1; then
  DOCKER=(docker)
else
  DOCKER=(sudo docker)
fi

cleanup() {
  "${DOCKER[@]}" rm -f "$NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

"${DOCKER[@]}" run -d --rm --name "$NAME" \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=boa_ml_studio \
  -p "127.0.0.1:${PORT}:5432" \
  "$IMAGE" >/dev/null

ready=false
for _ in $(seq 1 60); do
  if "${DOCKER[@]}" exec "$NAME" pg_isready -U postgres -d boa_ml_studio >/dev/null 2>&1; then
    ready=true
    break
  fi
  sleep 1
done
if [[ "$ready" != true ]]; then
  echo "PostgreSQL did not become ready" >&2
  exit 1
fi
"${DOCKER[@]}" exec "$NAME" pg_isready -U postgres -d boa_ml_studio

cd "$ROOT/database"
ALEMBIC="$ROOT/backend/.venv/bin/alembic"
if [[ ! -x "$ALEMBIC" ]]; then
  echo "Missing $ALEMBIC; run 'cd backend && uv sync --extra test' first" >&2
  exit 1
fi

current_revision() {
  DATABASE_URL="$URL" "$ALEMBIC" -c alembic.ini current | awk '{print $1}'
}

# Base vierge -> head.
DATABASE_URL="$URL" "$ALEMBIC" -c alembic.ini upgrade head
[[ "$(current_revision)" == "0019_ml_studio_catalog_merge" ]]

# Base existante au head -> upgrade idempotent sans changement.
DATABASE_URL="$URL" "$ALEMBIC" -c alembic.ini upgrade head
[[ "$(current_revision)" == "0019_ml_studio_catalog_merge" ]]

# Downgrade de la tranche, contrôle de disparition, puis ré-upgrade.
DATABASE_URL="$URL" "$ALEMBIC" -c alembic.ini downgrade 0017_ml_shadow_governance
[[ "$(current_revision)" == "0017_ml_shadow_governance" ]]
if "${DOCKER[@]}" exec "$NAME" psql -U postgres -d boa_ml_studio -Atqc \
  "SELECT to_regclass('ml.training_jobs') IS NULL AND to_regclass('ml.training_examples') IS NULL" \
  | grep -qx t; then
  :
else
  echo "Studio ML tables still present after downgrade" >&2
  exit 1
fi
DATABASE_URL="$URL" "$ALEMBIC" -c alembic.ini upgrade head
[[ "$(current_revision)" == "0019_ml_studio_catalog_merge" ]]

# Vérifications structurelles PostgreSQL finales.
"${DOCKER[@]}" exec "$NAME" psql -U postgres -d boa_ml_studio -Atqc \
  "SELECT count(*) FROM pg_indexes WHERE schemaname='ml' AND indexname='uq_ml_training_jobs_active_manifest'" \
  | grep -qx 1
"${DOCKER[@]}" exec "$NAME" psql -U postgres -d boa_ml_studio -Atqc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='ml' AND table_name IN ('training_jobs','training_examples')" \
  | grep -qx 2
"${DOCKER[@]}" exec "$NAME" psql -U postgres -d boa_ml_studio -Atqc \
  "SELECT count(*) FROM information_schema.columns WHERE table_schema='product' AND table_name='products' AND column_name IN ('family','description','source_url')" \
  | grep -qx 3

echo "POSTGRES_MIGRATIONS_PASS fresh=head existing=head downgrade=0017 reupgrade=head"
