"""Send reply use case - handles Instagram reply business logic."""

from typing import Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories.comment import CommentRepository
from ..repositories.answer import AnswerRepository
from ..services.instagram_service import InstagramGraphAPIService
from ..utils.decorators import handle_task_errors


class SendReplyUseCase:
    """Use case for sending replies to Instagram comments."""

    def __init__(self, session: AsyncSession, instagram_service=None):
        self.session = session
        self.comment_repo = CommentRepository(session)
        self.answer_repo = AnswerRepository(session)
        self.instagram_service = instagram_service or InstagramGraphAPIService()

    @handle_task_errors()
    async def execute(
        self,
        comment_id: str,
        reply_text: str = None,
        use_generated_answer: bool = True
    ) -> Dict[str, Any]:
        """Execute send reply use case."""
        # 1. Get comment
        comment = await self.comment_repo.get_by_id(comment_id)
        if not comment:
            return {"status": "error", "reason": f"Comment {comment_id} not found"}

        # 2. Determine reply text
        if use_generated_answer and not reply_text:
            answer_record = await self.answer_repo.get_by_comment_id(comment_id)
            if not answer_record or not answer_record.answer:
                return {"status": "error", "reason": "No generated answer available"}
            reply_text = answer_record.answer
        elif not reply_text:
            return {"status": "error", "reason": "No reply text provided"}

        # 3. Get answer record for tracking
        answer_record = await self.answer_repo.get_by_comment_id(comment_id)
        if not answer_record:
            answer_record = await self.answer_repo.create_for_comment(comment_id)

        # 4. Check if already sent
        if answer_record.reply_sent:
            return {
                "status": "skipped",
                "reason": "Reply already sent",
                "reply_id": answer_record.reply_id,
                "reply_sent_at": answer_record.reply_sent_at.isoformat() if answer_record.reply_sent_at else None,
            }

        # 5. Send reply via Instagram API
        result = await self.instagram_service.send_comment_reply(
            comment_id=comment_id,
            message=reply_text
        )

        # 6. Update tracking
        if result.get("success"):
            answer_record.reply_sent = True
            answer_record.reply_sent_at = datetime.utcnow()
            answer_record.reply_status = "sent"
            answer_record.reply_response = result.get("response", {})
            answer_record.reply_id = result.get("response", {}).get("id")
        else:
            answer_record.reply_status = "failed"
            answer_record.reply_error = result.get("error", "Unknown error")
            answer_record.reply_response = result

        await self.session.commit()

        return {
            "status": "success" if result.get("success") else "error",
            "reply_text": reply_text,
            "reply_sent": answer_record.reply_sent,
            "reply_id": answer_record.reply_id,
            "api_response": result,
        }
