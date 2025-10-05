"""Classification repository for comment classification data access."""

import logging
from typing import Optional, List
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from .base import BaseRepository
from ..models.comment_classification import CommentClassification, ProcessingStatus

logger = logging.getLogger(__name__)


class ClassificationRepository(BaseRepository[CommentClassification]):
    """Repository for comment classifications."""

    def __init__(self, session: AsyncSession):
        super().__init__(CommentClassification, session)

    async def get_by_comment_id(self, comment_id: str) -> Optional[CommentClassification]:
        """Get classification by comment ID."""
        result = await self.session.execute(
            select(CommentClassification).where(
                CommentClassification.comment_id == comment_id
            )
        )
        return result.scalar_one_or_none()

    async def get_pending_retries(self) -> List[CommentClassification]:
        """Get classifications pending retry."""
        result = await self.session.execute(
            select(CommentClassification).where(
                and_(
                    CommentClassification.processing_status == ProcessingStatus.RETRY,
                    CommentClassification.retry_count < CommentClassification.max_retries
                )
            )
        )
        return list(result.scalars().all())

    async def mark_processing(self, classification: CommentClassification, retry_count: int = 0):
        """Update classification to processing status."""
        from ..utils.time import now_db_utc
        classification.processing_status = ProcessingStatus.PROCESSING
        classification.processing_started_at = now_db_utc()
        classification.retry_count = retry_count
        await self.session.flush()

    async def mark_completed(self, classification: CommentClassification):
        """Update classification to completed status."""
        from ..utils.time import now_db_utc
        classification.processing_status = ProcessingStatus.COMPLETED
        classification.processing_completed_at = now_db_utc()
        classification.last_error = None
        await self.session.flush()

    async def mark_failed(self, classification: CommentClassification, error: str):
        """Update classification to failed status."""
        classification.processing_status = ProcessingStatus.FAILED
        classification.last_error = error
        await self.session.flush()
