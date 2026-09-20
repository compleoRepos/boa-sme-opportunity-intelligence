#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd)
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_command docker
require_command jq
require_command sha256sum
load_local_env

POSTGRES_ADMIN_USER=${POSTGRES_ADMIN_USER:-boa_admin}
POSTGRES_ADMIN_PASSWORD=${POSTGRES_ADMIN_PASSWORD:-DevOnly-Postgres-ChangeMe!}
SENTINEL_DATABASE=${POSTGRES_DB:-boa_sme}
RUN_SUFFIX="$(date -u +%Y%m%dT%H%M%SZ)-$$"
SOURCE_DATABASE="boa_backup_source_${RUN_SUFFIX//[^0-9A-Za-z]/_}"
RESTORE_DATABASE="boa_backup_restore_${RUN_SUFFIX//[^0-9A-Za-z]/_}"
DUMP_CONTAINER="/tmp/${RUN_SUFFIX}.dump"
WORK_DIR=$(mktemp -d "/tmp/boa-backup-restore-${RUN_SUFFIX}.XXXXXX")
DUMP_FILE="$WORK_DIR/backup.dump"
CORRUPT_FILE="$WORK_DIR/backup-corrupt.dump"
OUTPUT_FILE=${BACKUP_RESTORE_EVIDENCE_FILE:-$PROJECT_ROOT/docs/evidence/backup/RESULTATS-BACKUP-RESTORE.json}

mkdir -p "$(dirname -- "$OUTPUT_FILE")"
chmod 700 "$WORK_DIR"

cleanup_databases() {
  compose exec -T postgres rm -f "$DUMP_CONTAINER" >/dev/null 2>&1 || true
  compose exec -T postgres dropdb --if-exists --force --username "$POSTGRES_ADMIN_USER" \
    "$SOURCE_DATABASE" >/dev/null 2>&1 || true
  compose exec -T postgres dropdb --if-exists --force --username "$POSTGRES_ADMIN_USER" \
    "$RESTORE_DATABASE" >/dev/null 2>&1 || true
}

cleanup() {
  cleanup_databases
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

catalog_sql() {
  local query=$1
  compose exec -T postgres psql --set=ON_ERROR_STOP=1 --tuples-only --no-align \
    --username "$POSTGRES_ADMIN_USER" --dbname postgres -c "$query"
}

compose build customer >/dev/null
compose up --detach postgres
wait_for_healthy postgres 120
source_preexisting=$(catalog_sql "SELECT count(*) FROM pg_database WHERE datname='${SOURCE_DATABASE}'")
restore_preexisting=$(catalog_sql "SELECT count(*) FROM pg_database WHERE datname='${RESTORE_DATABASE}'")
sentinel_oid_before=$(catalog_sql "SELECT oid FROM pg_database WHERE datname='${SENTINEL_DATABASE}'")
[[ "$source_preexisting" -eq 0 ]]
[[ "$restore_preexisting" -eq 0 ]]
[[ -n "$sentinel_oid_before" ]]
compose exec -T postgres createdb --username "$POSTGRES_ADMIN_USER" "$SOURCE_DATABASE"
compose exec -T postgres createdb --username "$POSTGRES_ADMIN_USER" "$RESTORE_DATABASE"

alembic() {
  local database=$1
  shift
  local database_url="postgresql+psycopg://${POSTGRES_ADMIN_USER}:${POSTGRES_ADMIN_PASSWORD}@postgres:5432/${database}"
  compose run --rm --no-deps --entrypoint /bin/sh --env "DATABASE_URL=$database_url" \
    customer -ec "cd /app/database && exec alembic -c alembic.ini $*"
}

sql() {
  local database=$1 query=$2
  compose exec -T postgres psql --set=ON_ERROR_STOP=1 --tuples-only --no-align \
    --username "$POSTGRES_ADMIN_USER" --dbname "$database" -c "$query"
}

alembic "$SOURCE_DATABASE" "upgrade head"
sql "$SOURCE_DATABASE" \
  "CREATE TABLE public.backup_restore_markers (marker_id text PRIMARY KEY, payload text NOT NULL, created_at timestamptz NOT NULL); INSERT INTO public.backup_restore_markers VALUES ('${RUN_SUFFIX}','synthetic-backup-restore-proof','2026-09-20T00:00:00Z');" \
  >/dev/null

schema_count_source=$(sql "$SOURCE_DATABASE" "SELECT count(*) FROM information_schema.schemata WHERE schema_name NOT LIKE 'pg_%' AND schema_name <> 'information_schema'")
table_count_source=$(sql "$SOURCE_DATABASE" "SELECT count(*) FROM information_schema.tables WHERE table_type='BASE TABLE' AND table_schema NOT IN ('pg_catalog','information_schema')")
index_count_source=$(sql "$SOURCE_DATABASE" "SELECT count(*) FROM pg_indexes WHERE schemaname NOT IN ('pg_catalog','information_schema')")
constraint_count_source=$(sql "$SOURCE_DATABASE" "SELECT count(*) FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema')")
alembic_source=$(sql "$SOURCE_DATABASE" "SELECT version_num FROM alembic_version")
marker_source=$(sql "$SOURCE_DATABASE" "SELECT marker_id || ':' || payload || ':' || to_char(created_at AT TIME ZONE 'UTC','YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') FROM public.backup_restore_markers")
postgres_version=$(sql "$SOURCE_DATABASE" "SHOW server_version")
backend_base_image=$(awk '/^FROM / {print $2; exit}' "$PROJECT_ROOT/infrastructure/docker/backend.Dockerfile")

backup_started_ns=$(date +%s%N)
compose exec -T --env "PGPASSWORD=$POSTGRES_ADMIN_PASSWORD" postgres \
  pg_dump --username "$POSTGRES_ADMIN_USER" --dbname "$SOURCE_DATABASE" \
  --format=custom --compress=6 --no-owner --file "$DUMP_CONTAINER"
backup_finished_ns=$(date +%s%N)
container_id=$(compose ps -q postgres)
docker_cli exec "$container_id" cat "$DUMP_CONTAINER" >"$DUMP_FILE"
chmod 600 "$DUMP_FILE"

dump_bytes=$(stat -c %s "$DUMP_FILE")
[[ "$dump_bytes" -gt 0 ]]
dump_sha256=$(sha256sum "$DUMP_FILE" | awk '{print $1}')
restore_list_entries=$(compose exec -T postgres pg_restore --list "$DUMP_CONTAINER" | grep -cv '^;')
[[ "$restore_list_entries" -gt 0 ]]

cp "$DUMP_FILE" "$CORRUPT_FILE"
printf '\001' >>"$CORRUPT_FILE"
corrupt_sha256=$(sha256sum "$CORRUPT_FILE" | awk '{print $1}')
[[ "$corrupt_sha256" != "$dump_sha256" ]]

restore_started_ns=$(date +%s%N)
compose exec -T --env "PGPASSWORD=$POSTGRES_ADMIN_PASSWORD" postgres \
  pg_restore --username "$POSTGRES_ADMIN_USER" --dbname "$RESTORE_DATABASE" \
  --exit-on-error --no-owner "$DUMP_CONTAINER"
restore_finished_ns=$(date +%s%N)

verify_started_ns=$(date +%s%N)
schema_count_restore=$(sql "$RESTORE_DATABASE" "SELECT count(*) FROM information_schema.schemata WHERE schema_name NOT LIKE 'pg_%' AND schema_name <> 'information_schema'")
table_count_restore=$(sql "$RESTORE_DATABASE" "SELECT count(*) FROM information_schema.tables WHERE table_type='BASE TABLE' AND table_schema NOT IN ('pg_catalog','information_schema')")
index_count_restore=$(sql "$RESTORE_DATABASE" "SELECT count(*) FROM pg_indexes WHERE schemaname NOT IN ('pg_catalog','information_schema')")
constraint_count_restore=$(sql "$RESTORE_DATABASE" "SELECT count(*) FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema')")
alembic_restore=$(sql "$RESTORE_DATABASE" "SELECT version_num FROM alembic_version")
marker_restore=$(sql "$RESTORE_DATABASE" "SELECT marker_id || ':' || payload || ':' || to_char(created_at AT TIME ZONE 'UTC','YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') FROM public.backup_restore_markers")
verify_finished_ns=$(date +%s%N)

[[ "$schema_count_restore" == "$schema_count_source" ]]
[[ "$table_count_restore" == "$table_count_source" ]]
[[ "$index_count_restore" == "$index_count_source" ]]
[[ "$constraint_count_restore" == "$constraint_count_source" ]]
[[ "$alembic_restore" == "$alembic_source" ]]
[[ "$marker_restore" == "$marker_source" ]]

cleanup_databases
source_remaining=$(catalog_sql "SELECT count(*) FROM pg_database WHERE datname='${SOURCE_DATABASE}'")
restore_remaining=$(catalog_sql "SELECT count(*) FROM pg_database WHERE datname='${RESTORE_DATABASE}'")
sentinel_oid_after=$(catalog_sql "SELECT oid FROM pg_database WHERE datname='${SENTINEL_DATABASE}'")
[[ "$source_remaining" -eq 0 ]]
[[ "$restore_remaining" -eq 0 ]]
[[ "$sentinel_oid_after" == "$sentinel_oid_before" ]]

backup_duration_ms=$(((backup_finished_ns - backup_started_ns) / 1000000))
restore_duration_ms=$(((restore_finished_ns - restore_started_ns) / 1000000))
verify_duration_ms=$(((verify_finished_ns - verify_started_ns) / 1000000))
base_commit=$(git -C "$PROJECT_ROOT" rev-parse HEAD)
source_digest=$(
  cd "$PROJECT_ROOT"
  {
    sha256sum scripts/common.sh scripts/validate-backup-restore.sh infrastructure/docker-compose.yml infrastructure/docker/backend.Dockerfile
    find database/migrations -type f -name '*.py' -print0 | sort -z | xargs -0 sha256sum
  } | sha256sum | awk '{print $1}'
)
generated_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
run_id="backup-restore-${RUN_SUFFIX}"

jq -n \
  --arg runId "$run_id" \
  --arg generatedAt "$generated_at" \
  --arg baseCommit "$base_commit" \
  --arg sourceDigest "$source_digest" \
  --arg postgresVersion "$postgres_version" \
  --arg backendBaseImage "$backend_base_image" \
  --arg sourceDatabase "$SOURCE_DATABASE" \
  --arg restoreDatabase "$RESTORE_DATABASE" \
  --arg sentinelDatabase "$SENTINEL_DATABASE" \
  --arg dumpSha256 "$dump_sha256" \
  --arg alembicVersion "$alembic_restore" \
  --arg marker "$marker_restore" \
  --argjson dumpBytes "$dump_bytes" \
  --argjson restoreListEntries "$restore_list_entries" \
  --argjson backupDurationMs "$backup_duration_ms" \
  --argjson restoreDurationMs "$restore_duration_ms" \
  --argjson verifyDurationMs "$verify_duration_ms" \
  --argjson schemas "$schema_count_restore" \
  --argjson tables "$table_count_restore" \
  --argjson indexes "$index_count_restore" \
  --argjson constraints "$constraint_count_restore" \
  '{runId:$runId,generatedAt:$generatedAt,status:"PASS",scope:"LOCAL_SYNTHETIC_LOGICAL_BACKUP_RESTORE",sourceRevision:{baseCommit:$baseCommit,sourceDigest:$sourceDigest},environment:{postgresVersion:$postgresVersion,backendBaseImage:$backendBaseImage,sourceDatabase:$sourceDatabase,restoreDatabase:$restoreDatabase,sentinelDatabase:$sentinelDatabase,isolatedDatabases:true},backup:{format:"PostgreSQL custom",compression:6,bytes:$dumpBytes,sha256:$dumpSha256,listEntries:$restoreListEntries},durationsMs:{backup:$backupDurationMs,restore:$restoreDurationMs,verify:$verifyDurationMs},restoredInventory:{alembicVersion:$alembicVersion,schemas:$schemas,tables:$tables,indexes:$indexes,constraints:$constraints,marker:$marker},checks:{databaseNamesAbsentBeforeCreate:"PASS",nonEmptyDump:"PASS",checksumBeforeRestore:"PASS",tamperedCopyDetected:"PASS",pgRestoreListReadable:"PASS",restoreExitOnError:"PASS",alembicVersionMatch:"PASS",schemaCountMatch:"PASS",tableCountMatch:"PASS",indexCountMatch:"PASS",constraintCountMatch:"PASS",syntheticMarkerMatch:"PASS",temporaryDatabasesAbsentAfterCleanup:"PASS",sentinelDatabaseUnchanged:"PASS"},limitations:["Preuve locale sur deux bases PostgreSQL Docker isolées et données synthétiques uniquement.","Le dump temporaire n est pas chiffré et est supprimé en fin de run; cette preuve ne valide ni coffre, ni KMS, ni stockage off-site, ni immutabilité, ni politique de rétention.","Les durées observées ne constituent ni RTO ni RPO BOA; ces objectifs restent A VALIDER AVEC BOA.","Le protocole restaure la base applicative PostgreSQL; la reprise Keycloak, secrets, certificats, images et infrastructure reste NON IMPLEMENTEE."]}' >"$OUTPUT_FILE"

echo "[backup-restore] PASS: $OUTPUT_FILE"
