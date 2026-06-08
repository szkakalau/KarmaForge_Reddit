"""initial multi-user SaaS schema

Revision ID: d49abad38723
Revises: None
Create Date: 2026-06-06

Adds users.tier column, subscriptions table, subreddit_configs table.
Existing tables (posts, comments, users, generations, feedback) are
preserved — only net-new columns and tables are added.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d49abad38723"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Add tier column to existing users table ──
    # SQLite doesn't support IF NOT EXISTS for ALTER TABLE ADD COLUMN,
    # so we catch the duplicate column error gracefully.
    try:
        op.execute("ALTER TABLE users ADD COLUMN tier VARCHAR(16) DEFAULT 'free' NOT NULL")
    except Exception:
        pass  # column already exists

    # ── Create subscriptions table ──
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False, unique=True, index=True),
        sa.Column("stripe_customer_id", sa.String(64), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(64), nullable=True),
        sa.Column("plan", sa.String(16), nullable=False, server_default="free"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("current_period_start", sa.DateTime(), nullable=True),
        sa.Column("current_period_end", sa.DateTime(), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), default=False),
        sa.Column("stripe_event_ids", sa.JSON(), default=list),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    # ── Create subreddit_configs table ──
    op.create_table(
        "subreddit_configs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("subreddit", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("notes", sa.Text(), default=""),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("subreddit_configs")
    op.drop_table("subscriptions")
    # Note: we don't drop the tier column — it's safe to keep.
