"""Answer repository for data access layer."""

from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base import BaseRepository
from ..models.question_answer import QuestionAnswer, AnswerStatus


class AnswerRepository(BaseRepository[QuestionAnswer]):
    """Repository for QuestionAnswer operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(QuestionAnswer, session)

    async def get_by_comment_id(self, comment_id: str) -> Optional[QuestionAnswer]:
        """Get answer by comment ID."""
        result = await self.session.execute(
            select(QuestionAnswer).where(QuestionAnswer.comment_id == comment_id)
        )
        return result.scalar_one_or_none()

    async def create_for_comment(self, comment_id: str) -> QuestionAnswer:
        """Create a new answer record for a comment."""
        answer = QuestionAnswer(
            comment_id=comment_id,
            processing_status=AnswerStatus.PENDING
        )
        self.session.add(answer)
        await self.session.flush()
        return answer

    async def get_pending_answers(self, limit: int = 10) -> list[QuestionAnswer]:
        """Get pending answers for processing."""
        result = await self.session.execute(
            select(QuestionAnswer)
            .where(QuestionAnswer.processing_status == AnswerStatus.PENDING)
            .limit(limit)
        )
        return list(result.scalars().all())
