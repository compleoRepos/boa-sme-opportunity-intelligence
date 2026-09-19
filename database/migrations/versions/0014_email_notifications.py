"""Add governed SMTP notification delivery and immutable attempts."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014_email_notifications"
down_revision = "0013_label_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    outbox_columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("outbox_messages", schema="integration")
    }
    if "processing_status" not in outbox_columns:
        op.add_column(
            "outbox_messages",
            sa.Column("processing_status", sa.String(20)),
            schema="integration",
        )
    if "processing_error" not in outbox_columns:
        op.add_column(
            "outbox_messages",
            sa.Column("processing_error", sa.String(100)),
            schema="integration",
        )
    op.execute(sa.text("CREATE SCHEMA IF NOT EXISTS notification"))
    op.create_table(
        "notification_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("deduplication_key", sa.String(180), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True)),
        sa.Column("notification_type", sa.String(80), nullable=False),
        sa.Column("recipient_email", sa.String(254), nullable=False),
        sa.Column("recipient_name", sa.String(160)),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("text_body", sa.Text(), nullable=False),
        sa.Column("html_body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("provider_message_id", sa.String(255)),
        sa.Column("last_error", sa.String(500)),
        sa.Column("correlation_id", sa.String(100), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("created_by", sa.String(120), nullable=False),
        sa.UniqueConstraint("deduplication_key", name="uq_notification_messages_deduplication_key"),
        sa.CheckConstraint(
            "status IN ('PENDING','SENDING','RETRY','SENT','DELIVERY_UNCERTAIN','DEAD_LETTER')",
            name="ck_notification_messages_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0", name="ck_notification_messages_attempt_count_non_negative"
        ),
        sa.CheckConstraint(
            "max_attempts BETWEEN 1 AND 20", name="ck_notification_messages_max_attempts_range"
        ),
        schema="notification",
    )
    op.create_index(
        "ix_notification_due",
        "notification_messages",
        ["status", "next_attempt_at", "created_at"],
        schema="notification",
    )
    op.create_table(
        "notification_digest_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("relationship_manager_id", sa.String(120), nullable=False),
        sa.Column("recipient_email", sa.String(254), nullable=False),
        sa.Column(
            "timezone_name",
            sa.String(80),
            nullable=False,
            server_default="Africa/Abidjan",
        ),
        sa.Column("delivery_hour", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_digest_date", sa.Date()),
        sa.Column("last_notification_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("created_by", sa.String(120), nullable=False),
        sa.UniqueConstraint(
            "relationship_manager_id",
            name="uq_notification_digest_subscription_rm",
        ),
        sa.CheckConstraint(
            "delivery_hour BETWEEN 0 AND 23",
            name="ck_notification_digest_subscriptions_delivery_hour_range",
        ),
        schema="notification",
    )
    op.create_table(
        "notification_delivery_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "notification_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notification.notification_messages.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("provider_message_id", sa.String(255)),
        sa.Column("error_redacted", sa.String(500)),
        sa.Column(
            "attempted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "notification_id",
            "attempt_number",
            name="uq_notification_delivery_attempt_number",
        ),
        sa.CheckConstraint(
            "outcome IN ('SENT','FAILED','UNCERTAIN')",
            name="ck_notification_delivery_attempts_outcome",
        ),
        schema="notification",
    )
    op.create_index(
        "ix_notification_attempt_created",
        "notification_delivery_attempts",
        ["notification_id", "attempted_at"],
        schema="notification",
    )
    op.execute(
        sa.text(
            "CREATE OR REPLACE FUNCTION notification.prevent_delivery_attempt_mutation() "
            "RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION "
            "'notification_delivery_attempts is append-only'; END; $$"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER notification_attempts_immutable BEFORE UPDATE OR DELETE "
            "ON notification.notification_delivery_attempts FOR EACH ROW EXECUTE FUNCTION "
            "notification.prevent_delivery_attempt_mutation()"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER notification_attempts_no_truncate BEFORE TRUNCATE "
            "ON notification.notification_delivery_attempts FOR EACH STATEMENT EXECUTE FUNCTION "
            "notification.prevent_delivery_attempt_mutation()"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS notification_attempts_no_truncate "
            "ON notification.notification_delivery_attempts"
        )
    )
    op.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS notification_attempts_immutable "
            "ON notification.notification_delivery_attempts"
        )
    )
    op.execute(sa.text("DROP FUNCTION IF EXISTS notification.prevent_delivery_attempt_mutation()"))
    op.drop_table("notification_delivery_attempts", schema="notification")
    op.execute(sa.text("DROP TABLE IF EXISTS notification.notification_digest_subscriptions"))
    op.drop_table("notification_messages", schema="notification")
    op.execute(sa.text("DROP SCHEMA IF EXISTS notification"))
    outbox_columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("outbox_messages", schema="integration")
    }
    if "processing_error" in outbox_columns:
        op.drop_column("outbox_messages", "processing_error", schema="integration")
    if "processing_status" in outbox_columns:
        op.drop_column("outbox_messages", "processing_status", schema="integration")
