"""Comment repository for Instagram comment data access."""

import logging
from typing import Optional
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from .base import BaseRepository
from ..models.instagram_comment import InstagramComment
from ..models.comment_classification import CommentClassification, ProcessingStatus

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

    async def list_for_media(
        self,
        media_id: str,
        *,
        offset: int,
        limit: int,
        statuses: Optional[list[ProcessingStatus]] = None,
    ) -> list[InstagramComment]:
        stmt = (
            select(InstagramComment)
            .options(
                selectinload(InstagramComment.classification),
                selectinload(InstagramComment.question_answer),
            )
            .where(InstagramComment.media_id == media_id)
            .order_by(InstagramComment.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        if statuses:
            stmt = stmt.join(InstagramComment.classification).where(
                CommentClassification.processing_status.in_(statuses)
            )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_for_media(
        self,
        media_id: str,
        *,
        statuses: Optional[list[ProcessingStatus]] = None,
    ) -> int:
        if statuses:
            stmt = (
                select(func.count())
                .select_from(InstagramComment)
                .join(CommentClassification, InstagramComment.id == CommentClassification.comment_id)
                .where(
                    InstagramComment.media_id == media_id,
                    CommentClassification.processing_status.in_(statuses),
                )
            )
        else:
            stmt = select(func.count()).select_from(InstagramComment).where(InstagramComment.media_id == media_id)
        result = await self.session.execute(stmt)
        return result.scalar() or 0
