"""Comment repository for Instagram comment data access."""

import logging
from typing import Optional
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from .base import BaseRepository
from ..models.instagram_comment import InstagramComment

logger = logging.getLogger(__name__)


class CommentRepository(BaseRepository[InstagramComment]):
    """Repository for Instagram comments with relationships."""

    def __init__(self, session: AsyncSession):
        super().__init__(InstagramComment, session)

    async def get_with_classification(self, comment_id: str) -> Optional[InstagramComment]:
        """Get comment with classification eagerly loaded."""
        result = await self.session.execute(
            select(InstagramComment)
            .options(selectinload(InstagramComment.classification))
            .where(InstagramComment.id == comment_id)
        )
        return result.scalar_one_or_none()

    async def get_with_answer(self, comment_id: str) -> Optional[InstagramComment]:
        """Get comment with answer eagerly loaded."""
        result = await self.session.execute(
            select(InstagramComment)
            .options(selectinload(InstagramComment.question_answer))
            .where(InstagramComment.id == comment_id)
        )
        return result.scalar_one_or_none()

    async def get_full(self, comment_id: str) -> Optional[InstagramComment]:
        """Get comment with all relationships eagerly loaded."""
        result = await self.session.execute(
            select(InstagramComment)
            .options(
                selectinload(InstagramComment.classification),
                selectinload(InstagramComment.question_answer),
                selectinload(InstagramComment.media)
            )
            .where(InstagramComment.id == comment_id)
        )
        return result.scalar_one_or_none()
