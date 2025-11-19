"""add is_ai_generated flag to question answers

Revision ID: add_is_ai_generated_to_answers
Revises: add_moderation_action_flags
Create Date: 2025-11-18 15:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_is_ai_generated_to_answers"
down_revision: Union[str, Sequence[str], None] = "add_moderation_action_flags"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "question_messages_answers",
        sa.Column("is_ai_generated", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    answers_table = sa.table(
        "question_messages_answers",
        sa.column("id", sa.Integer),
        sa.column("meta_data", sa.JSON),
        sa.column("is_ai_generated", sa.Boolean),
    )
    conn = op.get_bind()
    rows = conn.execute(sa.select(answers_table.c.id, answers_table.c.meta_data)).fetchall()
    for row in rows:
        meta = row.meta_data or {}
        if isinstance(meta, dict) and meta.get("manual_patch"):
            conn.execute(
                answers_table.update()
                .where(answers_table.c.id == row.id)
                .values(is_ai_generated=False)
            )
    op.drop_column("question_messages_answers", "meta_data")


def downgrade() -> None:
    op.add_column(
        "question_messages_answers",
        sa.Column("meta_data", sa.JSON(), nullable=True),
    )
    op.drop_column("question_messages_answers", "is_ai_generated")
