"""Add Instagram metadata fields to OAuth tokens.

Revision ID: add_oauth_token_meta
Revises: make_oauth_refresh_token
Create Date: 2025-12-26 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "add_oauth_token_meta"
down_revision = "make_oauth_refresh_token"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "oauth_tokens",
        sa.Column("instagram_user_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "oauth_tokens",
        sa.Column("username", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("oauth_tokens", "username")
    op.drop_column("oauth_tokens", "instagram_user_id")
