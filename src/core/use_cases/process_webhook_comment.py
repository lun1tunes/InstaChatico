"""Process webhook comment use case - handles comment ingestion from Instagram webhooks."""

import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from ..models.instagram_comment import InstagramComment
from ..models.comment_classification import CommentClassification, ProcessingStatus
from ..repositories.comment import CommentRepository
from ..repositories.media import MediaRepository
from ..interfaces.services import IMediaService, ITaskQueue
from ..utils.time import now_db_utc

logger = logging.getLogger(__name__)


class ProcessWebhookCommentUseCase:
    """
    Process incoming comment from Instagram webhook.

    Follows Dependency Inversion Principle - depends on service protocols.

    Responsibilities:
    - Validate comment doesn't already exist
    - Ensure media exists (or create it)
    - Create comment and classification records
    - Queue classification task via ITaskQueue
    """

    def __init__(
        self,
        session: AsyncSession,
        media_service: IMediaService,
        task_queue: ITaskQueue,
    ):
        """
        Initialize use case with dependencies.

        Args:
            session: Database session
            media_service: Service implementing IMediaService protocol
            task_queue: Task queue implementing ITaskQueue protocol
        """
        self.session = session
        self.comment_repo = CommentRepository(session)
        self.media_repo = MediaRepository(session)
        self.media_service = media_service
        self.task_queue = task_queue

    async def execute(
        self,
        comment_id: str,
        media_id: str,
        user_id: str,
        username: str,
        text: str,
        entry_timestamp: int,
        parent_id: Optional[str] = None,
        raw_data: Optional[dict] = None,
    ) -> dict:
        """
        Process incoming webhook comment.

        Returns:
            {
                "status": "created" | "exists" | "error",
                "comment_id": str,
                "should_classify": bool,
                "reason": str (optional),
            }
        """
        try:
            # Check if comment already exists
            existing = await self.comment_repo.get_by_id(comment_id)
            if existing:
                logger.debug(f"Comment {comment_id} already exists")

                # Check if needs re-classification
                should_classify = (
                    not existing.classification
                    or existing.classification.processing_status != ProcessingStatus.COMPLETED
                )

                return {
                    "status": "exists",
                    "comment_id": comment_id,
                    "should_classify": should_classify,
                    "reason": "Comment already exists, may need re-classification",
                }

            # Ensure media exists
            media = await self.media_service.get_or_create_media(media_id, self.session)
            if not media:
                logger.error(f"Failed to create media {media_id}")
                return {
                    "status": "error",
                    "comment_id": comment_id,
                    "should_classify": False,
                    "reason": "Failed to create media record",
                }

            # Create comment record
            from datetime import datetime

            new_comment = InstagramComment(
                id=comment_id,
                media_id=media_id,
                user_id=user_id,
                username=username,
                text=text,
                created_at=datetime.fromtimestamp(entry_timestamp),
                parent_id=parent_id,
                raw_data=raw_data or {},
            )

            # Create classification record
            new_comment.classification = CommentClassification(comment_id=comment_id)

            self.session.add(new_comment)
            await self.session.commit()

            logger.info(f"Comment {comment_id} created successfully")
            return {
                "status": "created",
                "comment_id": comment_id,
                "should_classify": True,
                "reason": "New comment created",
            }

        except IntegrityError:
            await self.session.rollback()
            logger.warning(f"Comment {comment_id} inserted by another process (race condition)")
            return {
                "status": "exists",
                "comment_id": comment_id,
                "should_classify": False,
                "reason": "Race condition - inserted by another process",
            }

        except Exception as e:
            await self.session.rollback()
            logger.exception(f"Error processing comment {comment_id}")
            return {
                "status": "error",
                "comment_id": comment_id,
                "should_classify": False,
                "reason": f"Unexpected error: {str(e)}",
            }
