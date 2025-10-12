"""Use case for comment classification (Business Logic Layer)."""

import logging
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.comment_classification import CommentClassification, ProcessingStatus
from ..repositories.comment import CommentRepository
from ..repositories.classification import ClassificationRepository
from ..interfaces.services import IClassificationService, IMediaService
from ..utils.decorators import handle_task_errors

logger = logging.getLogger(__name__)


class ClassifyCommentUseCase:
    """
    Business logic for comment classification.

    Follows Single Responsibility Principle (SRP) and Dependency Inversion Principle (DIP).
    Depends on abstractions (protocols) rather than concrete implementations.
    """

    def __init__(
        self,
        session: AsyncSession,
        classification_service: IClassificationService,
        media_service: IMediaService,
    ):
        """
        Initialize use case with dependencies.

        Args:
            session: Database session
            classification_service: Service implementing IClassificationService protocol
            media_service: Service implementing IMediaService protocol
        """
        self.session = session
        self.comment_repo = CommentRepository(session)
        self.classification_repo = ClassificationRepository(session)
        self.classification_service = classification_service
        self.media_service = media_service

    @handle_task_errors()
    async def execute(self, comment_id: str, retry_count: int = 0) -> Dict[str, Any]:
        """
        Execute comment classification use case.

        Simplified logic - no infrastructure concerns.
        """
        # 1. Get comment with classification
        comment = await self.comment_repo.get_with_classification(comment_id)
        if not comment:
            logger.warning(f"Comment {comment_id} not found")
            return {"status": "error", "reason": "comment_not_found"}

        # 2. Ensure media exists
        media = await self.media_service.get_or_create_media(comment.media_id, self.session)
        if not media:
            logger.error(f"Failed to get media {comment.media_id}")
            return {"status": "error", "reason": "media_unavailable"}

        # 3. Wait for media context if needed
        if await self._should_wait_for_media_context(media):
            logger.info(f"Media {media.id} context not ready")
            return {"status": "retry", "reason": "waiting_for_media_context"}

        # 4. Get or create classification record
        classification = await self._get_or_create_classification(comment_id)

        # 5. Update status to processing
        await self.classification_repo.mark_processing(classification, retry_count)
        await self.session.commit()

        # 6. Generate conversation ID
        conversation_id = self.classification_service._generate_conversation_id(
            comment.id, comment.parent_id
        )
        comment.conversation_id = conversation_id

        # 7. Build media context
        media_context = self._build_media_context(media)

        # 8. Classify comment
        result = await self.classification_service.classify_comment(
            comment.text, conversation_id, media_context
        )

        # 9. Save results
        classification.classification = result.classification
        classification.confidence = result.confidence
        classification.reasoning = result.reasoning
        classification.input_tokens = result.input_tokens
        classification.output_tokens = result.output_tokens

        if result.error:
            await self.classification_repo.mark_failed(classification, result.error)
        else:
            await self.classification_repo.mark_completed(classification)

        await self.session.commit()

        logger.info(f"Comment {comment_id} classified: {result.classification}")

        return {
            "status": "success",
            "comment_id": comment_id,
            "classification": result.classification,
            "confidence": result.confidence,
        }

    async def _get_or_create_classification(self, comment_id: str) -> CommentClassification:
        """Get existing or create new classification record."""
        classification = await self.classification_repo.get_by_comment_id(comment_id)

        if not classification:
            classification = CommentClassification(comment_id=comment_id)
            await self.classification_repo.create(classification)

        return classification

    async def _should_wait_for_media_context(self, media) -> bool:
        """Check if we need to wait for media context analysis."""
        has_image = media.media_type in ["IMAGE", "CAROUSEL_ALBUM"]
        has_url = bool(media.media_url)
        no_context = not media.media_context

        return has_image and has_url and no_context

    def _build_media_context(self, media) -> Dict[str, Any]:
        """Build media context dictionary."""
        return {
            "caption": media.caption,
            "media_type": media.media_type,
            "media_context": media.media_context,
            "username": media.username,
            "comments_count": media.comments_count,
            "like_count": media.like_count,
            "permalink": media.permalink,
            "media_url": media.media_url,
            "is_comment_enabled": media.is_comment_enabled,
        }
