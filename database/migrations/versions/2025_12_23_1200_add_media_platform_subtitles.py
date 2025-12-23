"""add platform and subtitles to media

Revision ID: add_media_platform_subtitles
Revises: rename_comments_table
Create Date: 2025-12-23 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "add_media_platform_subtitles"
down_revision = "rename_comments_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "media",
        sa.Column(
            "platform",
            sa.String(length=20),
            nullable=False,
            server_default="instagram",
        ),
    )
    op.add_column(
        "media",
        sa.Column("subtitles", sa.Text(), nullable=True),
    )
    # Use IF NOT EXISTS to tolerate partial/previous runs.
    op.execute("CREATE INDEX IF NOT EXISTS ix_media_platform ON media (platform)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_media_platform")
    op.drop_column("media", "subtitles")
    op.drop_column("media", "platform")
