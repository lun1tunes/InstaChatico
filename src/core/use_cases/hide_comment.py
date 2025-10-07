"""Hide comment use case - handles comment hiding business logic."""

from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories.comment import CommentRepository
from ..services.instagram_service import InstagramGraphAPIService
from ..utils.decorators import handle_task_errors
from ..utils.time import now_db_utc


class HideCommentUseCase:
    """Use case for hiding Instagram comments."""

    def __init__(self, session: AsyncSession, instagram_service=None):
        self.session = session
        self.comment_repo = CommentRepository(session)
        self.instagram_service = instagram_service or InstagramGraphAPIService()

    @handle_task_errors()
    async def execute(self, comment_id: str, hide: bool = True) -> Dict[str, Any]:
        """Execute hide/unhide comment use case."""
        # 1. Get comment
        comment = await self.comment_repo.get_by_id(comment_id)
        if not comment:
            return {"status": "error", "reason": f"Comment {comment_id} not found"}

        # 2. Check current state
        if comment.is_hidden == hide:
            status = "hidden" if hide else "visible"
            return {
                "status": "skipped",
                "reason": f"Comment already {status}",
                "is_hidden": comment.is_hidden,
            }

        # 3. Hide/unhide via Instagram API
        result = await self.instagram_service.hide_comment(comment_id, hide=hide)

        if not result.get("success"):
            return {
                "status": "error",
                "reason": result.get("error", "Failed to hide comment"),
                "api_response": result,
            }

        # 4. Update database
        comment.is_hidden = hide
        comment.hidden_at = now_db_utc() if hide else None
        await self.session.commit()

        return {
            "status": "success",
            "action": "hidden" if hide else "unhidden",
            "is_hidden": comment.is_hidden,
            "hidden_at": comment.hidden_at.isoformat() if comment.hidden_at else None,
            "api_response": result,
        }
