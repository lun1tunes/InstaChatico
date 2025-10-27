"""Rename media.timestamp to media.posted_at

Revision ID: rename_media_timestamp_to_posted_at
Revises: sync_retry_defaults
Create Date: 2025-10-30 13:45:00.000000
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "rename_media_timestamp_to_posted_at"
down_revision: Union[str, Sequence[str], None] = "sync_retry_defaults"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename media.timestamp column to media.posted_at."""
    op.alter_column("media", "timestamp", new_column_name="posted_at")


def downgrade() -> None:
    """Revert media.posted_at column back to media.timestamp."""
    op.alter_column("media", "posted_at", new_column_name="timestamp")
