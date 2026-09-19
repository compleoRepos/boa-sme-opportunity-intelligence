#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/common.sh
source "$SCRIPT_DIR/common.sh"

mailpit_url=${MAILPIT_URL:-http://127.0.0.1:8025}
recipient="notification-proof-$(date +%s%N)@synthetic.invalid"
correlation="notification-proof-$(date +%s%N)"

curl -fsS -X DELETE "$mailpit_url/api/v1/messages" >/dev/null

event_id=$(
  compose exec -T postgres psql -U "${POSTGRES_ADMIN_USER:-boa_admin}" \
    -d "${POSTGRES_DB:-boa_sme}" -qAtc "
      INSERT INTO integration.outbox_messages (
        id, event_type, aggregate_type, aggregate_id, payload_json,
        correlation_id, causation_id, occurred_at, attempt_count
      ) VALUES (
        gen_random_uuid(), 'ACTION_NOTIFICATION_REQUESTED', 'PROOF', '$correlation',
        jsonb_build_object(
          'actionType', 'CONTACT_CUSTOMER',
          'opportunityId', 'OPP-PROOF',
          'dueAt', '2030-10-30T09:00:00+00:00',
          'recipientEmail', '$recipient',
          'recipientName', 'Preuve reproductible'
        ),
        '$correlation', '$correlation', now(), 0
      ) RETURNING id;"
)

status=""
for _attempt in $(seq 1 30); do
  status=$(
    compose exec -T postgres psql -U "${POSTGRES_ADMIN_USER:-boa_admin}" \
      -d "${POSTGRES_DB:-boa_sme}" -Atc "
        SELECT status
        FROM notification.notification_messages
        WHERE event_id = '$event_id';"
  )
  [[ "$status" == "SENT" ]] && break
  sleep 1
done

if [[ "$status" != "SENT" ]]; then
  echo "FAIL: notification $event_id did not reach SENT (status=${status:-missing})" >&2
  exit 1
fi

attempts=$(
  compose exec -T postgres psql -U "${POSTGRES_ADMIN_USER:-boa_admin}" \
    -d "${POSTGRES_DB:-boa_sme}" -Atc "
      SELECT count(*)
      FROM notification.notification_delivery_attempts a
      JOIN notification.notification_messages n ON n.id = a.notification_id
      WHERE n.event_id = '$event_id' AND a.outcome = 'SENT';"
)
mailpit_count=$(curl -fsS "$mailpit_url/api/v1/messages" | jq --arg recipient "$recipient" '[.messages[] | select(.To[].Address == $recipient)] | length')

[[ "$attempts" == "1" ]] || { echo "FAIL: expected one SENT attempt, got $attempts" >&2; exit 1; }
[[ "$mailpit_count" == "1" ]] || { echo "FAIL: expected one SMTP message, got $mailpit_count" >&2; exit 1; }

if compose exec -T postgres psql -v ON_ERROR_STOP=1 \
  -U "${POSTGRES_ADMIN_USER:-boa_admin}" -d "${POSTGRES_DB:-boa_sme}" \
  -c "UPDATE notification.notification_delivery_attempts SET outcome='FAILED' WHERE notification_id IN (SELECT id FROM notification.notification_messages WHERE event_id='$event_id');" \
  >/dev/null 2>&1; then
  echo "FAIL: delivery history accepted a mutation" >&2
  exit 1
fi

privileges=$(
  compose exec -T postgres psql -U "${POSTGRES_ADMIN_USER:-boa_admin}" \
    -d "${POSTGRES_DB:-boa_sme}" -Atc "
      SELECT concat_ws('|',
        has_schema_privilege('notification_service', 'notification', 'USAGE'),
        has_schema_privilege('notification_service', 'notification', 'CREATE'),
        has_table_privilege('notification_service', 'notification.notification_messages', 'INSERT'),
        has_table_privilege('notification_service', 'notification.notification_messages', 'DELETE'),
        has_table_privilege('notification_service', 'notification.notification_delivery_attempts', 'INSERT'),
        has_table_privilege('notification_service', 'notification.notification_delivery_attempts', 'UPDATE'),
        has_column_privilege('notification_service', 'integration.outbox_messages', 'published_at', 'UPDATE'),
        has_column_privilege('notification_service', 'integration.outbox_messages', 'payload_json', 'UPDATE')
      );"
)
[[ "$privileges" == "t|f|t|f|t|f|t|f" ]] || {
  echo "FAIL: unexpected notification_service privileges: $privileges" >&2
  exit 1
}

unrelated_visible=$(
  compose exec -T postgres psql -U "${POSTGRES_ADMIN_USER:-boa_admin}" \
    -d "${POSTGRES_DB:-boa_sme}" -qAtc "
      SET ROLE notification_service;
      SELECT count(*) FROM integration.outbox_messages
      WHERE event_type = 'PORTFOLIO_ASSIGNMENT_CHANGED';"
)
[[ "$unrelated_visible" == "0" ]] || {
  echo "FAIL: notification_service can read unrelated outbox rows" >&2
  exit 1
}

if compose exec -T postgres psql -v ON_ERROR_STOP=1 \
  -U "${POSTGRES_ADMIN_USER:-boa_admin}" -d "${POSTGRES_DB:-boa_sme}" \
  -c "SET ROLE notification_service; UPDATE integration.outbox_messages SET payload_json='{}'::jsonb WHERE id='$event_id';" \
  >/dev/null 2>&1; then
  echo "FAIL: notification_service can rewrite outbox payloads" >&2
  exit 1
fi

echo "PASS notification=$event_id status=$status sentAttempts=$attempts smtpMessages=$mailpit_count appendOnly=true leastPrivilege=true outboxRls=true"
