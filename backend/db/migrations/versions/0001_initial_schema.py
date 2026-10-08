"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "courts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("court_type", sa.String(50), nullable=False, server_default="other"),
        sa.Column("state", sa.String(2), nullable=True),
        sa.Column("category", sa.String(50), nullable=False, server_default="all"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("js_required", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("css_selector", sa.String(500), nullable=True),
        sa.Column("last_scanned_at", sa.DateTime(), nullable=True),
        sa.Column("last_content_hash", sa.String(64), nullable=True),
        sa.Column("last_changed_at", sa.DateTime(), nullable=True),
        sa.Column("consecutive_errors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("GETUTCDATE()"),
        ),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url", name="uq_courts_url"),
    )

    op.create_table(
        "scan_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("court_id", sa.Integer(), nullable=False),
        sa.Column("scanned_at", sa.DateTime(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="success"),
        sa.Column("error_message", sa.String(1000), nullable=True),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["court_id"], ["courts.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_scan_history_court_id", "scan_history", ["court_id"], unique=False
    )
    op.create_index(
        "ix_scan_history_scanned_at", "scan_history", ["scanned_at"], unique=False
    )

    op.create_table(
        "changes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("court_id", sa.Integer(), nullable=False),
        sa.Column("detected_at", sa.DateTime(), nullable=False),
        sa.Column("old_snapshot_path", sa.String(500), nullable=False),
        sa.Column("new_snapshot_path", sa.String(500), nullable=False),
        sa.Column("diff_text", sa.Text(), nullable=True),
        sa.Column("diff_line_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ai_is_relevant", sa.Boolean(), nullable=True),
        sa.Column("ai_summary", sa.String(1000), nullable=True),
        sa.Column("ai_category", sa.String(50), nullable=True),
        sa.Column("ai_priority", sa.String(20), nullable=True),
        sa.Column("ai_action", sa.String(1000), nullable=True),
        sa.Column("sharepoint_item_id", sa.String(200), nullable=True),
        sa.Column("email_sent", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="new"),
        sa.Column("reviewed_by", sa.String(255), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["court_id"], ["courts.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_changes_court_id", "changes", ["court_id"], unique=False
    )
    op.create_index(
        "ix_changes_detected_at", "changes", ["detected_at"], unique=False
    )
    op.create_index(
        "ix_changes_status", "changes", ["status"], unique=False
    )

    op.create_table(
        "alert_config",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email_recipients", sa.String(2000), nullable=False, server_default=""),
        sa.Column("notify_immediately", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("notify_digest_time", sa.String(10), nullable=True),
        sa.Column("min_priority", sa.String(10), nullable=False, server_default="low"),
        sa.Column("ai_filter_enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
    )
    # Insert default config row
    op.execute(
        "INSERT INTO alert_config (email_recipients, notify_immediately, "
        "min_priority, ai_filter_enabled) VALUES ('', 1, 'low', 1)"
    )


def downgrade() -> None:
    op.drop_table("alert_config")
    op.drop_index("ix_changes_status", table_name="changes")
    op.drop_index("ix_changes_detected_at", table_name="changes")
    op.drop_index("ix_changes_court_id", table_name="changes")
    op.drop_table("changes")
    op.drop_index("ix_scan_history_scanned_at", table_name="scan_history")
    op.drop_index("ix_scan_history_court_id", table_name="scan_history")
    op.drop_table("scan_history")
    op.drop_table("courts")
