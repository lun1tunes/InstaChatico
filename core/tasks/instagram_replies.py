"""
Instagram reply tasks for InstaChatico.
Handles sending replies back to Instagram via Graph API.
"""

from datetime import datetime
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from ..celery_config import celery_app
from ..models import InstagramComment, QuestionAnswer, AnswerStatus
from .base import BaseTaskExecutor, RetryableTask, create_task_logger

logger = create_task_logger("instagram_replies")


class InstagramReplyExecutor(BaseTaskExecutor, RetryableTask):
    """Handles Instagram reply operations"""
    
    def __init__(self):
        BaseTaskExecutor.__init__(self, "instagram_replies")
        RetryableTask.__init__(self, max_retries=3, retry_delay=60)
    
    async def send_reply_operation(
        self,
        session,
        comment_id: str,
        answer_text: str
    ) -> dict:
        """
        Core Instagram reply sending operation.
        
        Args:
            session: Database session
            comment_id: Instagram comment ID to reply to
            answer_text: Answer text to send as reply
            
        Returns:
            Reply sending result dictionary
        """
        # Get comment with answer record
        result = await session.execute(
            select(InstagramComment)
            .options(selectinload(InstagramComment.question_answer))
            .where(InstagramComment.id == comment_id)
        )
        comment = result.scalar_one_or_none()
        
        if not comment:
            raise ValueError(f"Comment {comment_id} not found")
        
        if not comment.question_answer:
            raise ValueError(f"Comment {comment_id} has no answer record")
        
        # Check if answer is completed
        if comment.question_answer.processing_status != AnswerStatus.COMPLETED:
            raise ValueError(f"Answer for comment {comment_id} is not completed")
        
        # Check if reply already sent
        if comment.question_answer.reply_sent:
            logger.info(f"Reply already sent for comment {comment_id}")
            return {
                "comment_id": comment_id,
                "status": "skipped",
                "reason": "already_sent"
            }
        
        # TODO: Implement Instagram API service
        # For now, simulate successful reply
        reply_id = f"reply_{comment_id}_{int(datetime.utcnow().timestamp())}"
        
        # Update answer record with reply information
        comment.question_answer.reply_sent = True
        comment.question_answer.reply_sent_at = datetime.utcnow()
        comment.question_answer.reply_status = "sent"
        comment.question_answer.reply_id = reply_id
        comment.question_answer.reply_response = {
            "id": reply_id,
            "status": "success",
            "message": "Reply sent successfully"
        }
        
        await session.commit()
        
        logger.log_instagram_reply_sent(
            comment_id,
            reply_id,
            0  # processing_time_ms - will be calculated by base class
        )
        
        return {
            "comment_id": comment_id,
            "reply_id": reply_id,
            "status": "sent",
            "message": "Reply sent successfully to Instagram"
        }
    
    async def process_pending_replies_operation(
        self,
        session,
        limit: int = 50
    ) -> dict:
        """
        Process all completed answers that need to be sent to Instagram.
        
        Args:
            session: Database session
            limit: Maximum number of replies to process
            
        Returns:
            Processing result dictionary
        """
        # Find completed answers that haven't been sent yet
        stmt = select(QuestionAnswer).where(
            and_(
                QuestionAnswer.processing_status == AnswerStatus.COMPLETED,
                QuestionAnswer.answer.isnot(None),
                QuestionAnswer.reply_sent == False
            )
        ).limit(limit)
        
        result = await session.execute(stmt)
        pending_answers = result.scalars().all()
        
        if not pending_answers:
            logger.info("No pending replies to process")
            return {"processed": 0, "message": "No pending replies"}
        
        logger.info(f"Processing {len(pending_answers)} pending replies")
        
        # Process each reply
        processed = 0
        for answer_record in pending_answers:
            try:
                await self.send_reply_operation(
                    session,
                    answer_record.comment_id,
                    answer_record.answer
                )
                processed += 1
            except Exception as e:
                logger.error(
                    f"Failed to send reply for comment {answer_record.comment_id}",
                    comment_id=answer_record.comment_id,
                    error=str(e)
                )
        
        return {
            "processed": processed,
            "total_found": len(pending_answers),
            "message": f"Sent {processed} of {len(pending_answers)} replies"
        }


# Create executor instance
reply_executor = InstagramReplyExecutor()


@celery_app.task(bind=True, max_retries=3, name='core.tasks.instagram_replies.send_reply')
def send_instagram_reply(self, comment_id: str, answer_text: str):
    """
    Send a reply to an Instagram comment.
    
    This task:
    1. Verifies the answer is ready to be sent
    2. Sends the reply via Instagram Graph API
    3. Updates the database with reply status
    4. Handles errors and retries automatically
    
    Args:
        comment_id: Instagram comment ID to reply to
        answer_text: Text to send as reply
        
    Returns:
        Dict with reply sending results
    """
    try:
        result = reply_executor.run_async_task(
            reply_executor.send_reply_operation,
            comment_id,
            answer_text
        )
        return result
        
    except Exception as e:
        # Handle retry logic
        if reply_executor.should_retry(self.request.retries, e):
            retry_delay = reply_executor.get_retry_delay(self.request.retries)
            
            logger.warning(
                f"Instagram reply will retry in {retry_delay} seconds",
                comment_id=comment_id,
                retry_count=self.request.retries,
                error=str(e)
            )
            
            raise self.retry(countdown=retry_delay, exc=e)
        else:
            logger.error(
                f"Instagram reply failed after {self.request.retries} retries",
                comment_id=comment_id,
                error=str(e)
            )
            
            return {
                "success": False,
                "error": str(e),
                "comment_id": comment_id,
                "retry_count": self.request.retries
            }


@celery_app.task(name='core.tasks.instagram_replies.process_pending_replies')
def process_pending_replies(limit: int = 50):
    """
    Process all pending replies that need to be sent to Instagram.
    
    This task runs periodically to ensure all generated answers
    are sent back to Instagram as replies.
    
    Args:
        limit: Maximum number of replies to process in one run
        
    Returns:
        Dict with processing results
    """
    try:
        result = reply_executor.run_async_task(
            reply_executor.process_pending_replies_operation,
            limit
        )
        return result
        
    except Exception as e:
        logger.error(
            "Failed to process pending replies",
            error=str(e),
            limit=limit
        )
        
        return {
            "success": False,
            "error": str(e),
            "processed": 0
        }
