"""Send Telegram notification use case - handles notification business logic."""

from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories.comment import CommentRepository
from ..services.telegram_alert_service import TelegramAlertService
from ..utils.decorators import handle_task_errors


class SendTelegramNotificationUseCase:
    """Use case for sending Telegram notifications for urgent/critical comments."""

    def __init__(self, session: AsyncSession, telegram_service=None):
        self.session = session
        self.comment_repo = CommentRepository(session)
        self.telegram_service = telegram_service or TelegramAlertService()

    @handle_task_errors()
    async def execute(self, comment_id: str) -> Dict[str, Any]:
        """Execute Telegram notification use case."""
        # 1. Get comment with classification
        comment = await self.comment_repo.get_with_classification(comment_id)
        if not comment:
            return {"status": "error", "reason": f"Comment {comment_id} not found"}

        if not comment.classification:
            return {"status": "error", "reason": "no_classification"}

        # 2. Check if notification is needed
        classification = comment.classification.classification.lower()
        notify_classifications = [
            "urgent issue / complaint",
            "critical feedback",
            "partnership proposal",
        ]

        if classification not in notify_classifications:
            return {
                "status": "skipped",
                "reason": "no_notification_needed",
                "classification": classification,
            }

        # 3. Prepare notification data
        comment_data = {
            "comment_id": comment.id,
            "comment_text": comment.text,
            "classification": comment.classification.classification,
            "confidence": comment.classification.confidence,
            "reasoning": comment.classification.reasoning,
            "media_id": comment.media_id,
            "username": comment.username,
            "user_id": comment.user_id,
            "created_at": comment.created_at.isoformat() if comment.created_at else None,
        }

        # 4. Send notification via Telegram
        result = await self.telegram_service.send_notification(comment_data)

        if result.get("success"):
            return {
                "status": "success",
                "comment_id": comment_id,
                "classification": classification,
                "telegram_result": result,
            }
        else:
            return {
                "status": "error",
                "reason": result.get("error", "Unknown error"),
                "telegram_result": result,
            }
