"""Rename instagram_comments table to comments for multi-platform support.

Revision ID: rename_comments_table
Revises: split_oauth_token_expiry_fields
Create Date: 2025-12-22 00:00:00
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "rename_comments_table"
down_revision = "split_oauth_token_expiry_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table("instagram_comments", "comments")
    # Keep index names aligned with the new table name for clarity.
    # Alembic versions prior to 1.12 don't expose op.rename_index, so use SQL.
    op.execute("ALTER INDEX IF EXISTS ix_instagram_comments_parent_id RENAME TO ix_comments_parent_id")
    op.execute("ALTER INDEX IF EXISTS ix_instagram_comments_conversation_id RENAME TO ix_comments_conversation_id")
    op.execute("ALTER INDEX IF EXISTS ix_instagram_comments_platform RENAME TO ix_comments_platform")


def downgrade() -> None:
    op.execute("ALTER INDEX IF EXISTS ix_comments_parent_id RENAME TO ix_instagram_comments_parent_id")
    op.execute("ALTER INDEX IF EXISTS ix_comments_conversation_id RENAME TO ix_instagram_comments_conversation_id")
    op.execute("ALTER INDEX IF EXISTS ix_comments_platform RENAME TO ix_instagram_comments_platform")
    op.rename_table("comments", "instagram_comments")
