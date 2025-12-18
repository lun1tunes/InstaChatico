"""Split OAuth token expiry fields into access/refresh.

Revision ID: split_oauth_token_expiry_fields
Revises: add_comment_platform
Create Date: 2025-12-16 17:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "split_oauth_token_expiry_fields"
down_revision = "add_comment_platform"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_oauth_tokens_expires_at", table_name="oauth_tokens")
    op.alter_column(
        "oauth_tokens",
        "expires_at",
        new_column_name="access_token_expires_at",
        existing_type=sa.DateTime(),
        existing_nullable=True,
    )
    op.create_index(
        "ix_oauth_tokens_access_token_expires_at",
        "oauth_tokens",
        ["access_token_expires_at"],
    )

    op.add_column(
        "oauth_tokens",
        sa.Column(
            "refresh_token_expires_at",
            sa.DateTime(),
            nullable=True,
            comment="Refresh token expiry time (if provided by Google)",
        ),
    )


def downgrade() -> None:
    op.drop_column("oauth_tokens", "refresh_token_expires_at")
    op.drop_index("ix_oauth_tokens_access_token_expires_at", table_name="oauth_tokens")
    op.alter_column(
        "oauth_tokens",
        "access_token_expires_at",
        new_column_name="expires_at",
        existing_type=sa.DateTime(),
        existing_nullable=True,
    )
    op.create_index("ix_oauth_tokens_expires_at", "oauth_tokens", ["expires_at"])

