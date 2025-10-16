"""Hide comment use case - handles comment hiding business logic."""

import logging
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories.comment import CommentRepository
from ..interfaces.services import IInstagramService
from ..utils.decorators import handle_task_errors
from ..utils.time import now_db_utc

logger = logging.getLogger(__name__)


class HideCommentUseCase:
    """
    Use case for hiding Instagram comments.

    Follows Dependency Inversion Principle - depends on IInstagramService protocol.
    """

    def __init__(self, session: AsyncSession, instagram_service: IInstagramService):
        """
        Initialize use case with dependencies.

        Args:
            session: Database session
            instagram_service: Service implementing IInstagramService protocol
        """
        self.session = session
        self.comment_repo = CommentRepository(session)
        self.instagram_service = instagram_service

    @handle_task_errors()
    async def execute(self, comment_id: str, hide: bool = True) -> Dict[str, Any]:
        """Execute hide/unhide comment use case."""
        logger.info(f"Starting hide/unhide comment | comment_id={comment_id} | hide={hide}")

        # 1. Get comment
        comment = await self.comment_repo.get_by_id(comment_id)
        if not comment:
            logger.error(f"Comment not found | comment_id={comment_id} | operation=hide_comment")
            return {"status": "error", "reason": f"Comment {comment_id} not found"}

        # 2. Check current state
        if comment.is_hidden == hide:
            status = "hidden" if hide else "visible"
            logger.info(f"Comment already in desired state | comment_id={comment_id} | status={status}")
            return {
                "status": "skipped",
                "reason": f"Comment already {status}",
                "is_hidden": comment.is_hidden,
            }

        # 3. Hide/unhide via Instagram API
        logger.info(f"Calling Instagram API to hide comment | comment_id={comment_id} | hide={hide}")
        result = await self.instagram_service.hide_comment(comment_id, hide=hide)

        if not result.get("success"):
            logger.error(
                f"Failed to hide comment via API | comment_id={comment_id} | "
                f"hide={hide} | error={result.get('error', 'Failed to hide comment')}"
            )
            return {
                "status": "error",
                "reason": result.get("error", "Failed to hide comment"),
                "api_response": result,
            }

        # 4. Update database
        logger.info(f"Updating comment hidden status in database | comment_id={comment_id} | hide={hide}")
        comment.is_hidden = hide
        comment.hidden_at = now_db_utc() if hide else None
        await self.session.commit()

        logger.info(f"Comment hidden status updated | comment_id={comment_id} | is_hidden={hide}")

        return {
            "status": "success",
            "action": "hidden" if hide else "unhidden",
            "is_hidden": comment.is_hidden,
            "hidden_at": comment.hidden_at.isoformat() if comment.hidden_at else None,
            "api_response": result,
        }
