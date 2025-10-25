"""add is_processing_enabled to media

Revision ID: add_is_processing_enabled_to_media
Revises: 354c49e45a72
Create Date: 2025-10-26 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_is_processing_enabled_to_media'
down_revision: Union[str, Sequence[str], None] = '354c49e45a72'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'media',
        sa.Column('is_processing_enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.execute("UPDATE media SET is_processing_enabled = TRUE WHERE is_processing_enabled IS NULL")


def downgrade() -> None:
    op.drop_column('media', 'is_processing_enabled')
