"""add comment platform column

Revision ID: add_comment_platform
Revises: add_oauth_tokens_table
Create Date: 2025-12-10 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "add_comment_platform"
down_revision = "add_title_to_media"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "instagram_comments",
        sa.Column(
            "platform",
            sa.String(length=20),
            nullable=False,
            server_default="instagram",
            comment="Origin platform of the comment (instagram|youtube|...)",
        ),
    )
    op.create_index("ix_instagram_comments_platform", "instagram_comments", ["platform"])
    # Drop server default to avoid future inserts relying on it implicitly
    op.alter_column("instagram_comments", "platform", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_instagram_comments_platform", table_name="instagram_comments")
    op.drop_column("instagram_comments", "platform")
