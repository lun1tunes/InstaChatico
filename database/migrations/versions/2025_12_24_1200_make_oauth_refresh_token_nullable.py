"""Make OAuth refresh token nullable for providers without refresh tokens.

Revision ID: make_oauth_refresh_token
Revises: add_media_platform_subtitles
Create Date: 2025-12-24 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "make_oauth_refresh_token"
down_revision = "add_media_platform_subtitles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "oauth_tokens",
        "refresh_token_encrypted",
        existing_type=sa.String(length=2048),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "oauth_tokens",
        "refresh_token_encrypted",
        existing_type=sa.String(length=2048),
        nullable=False,
    )
