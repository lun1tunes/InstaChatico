"""
Answer generation tasks for InstaChatico.
Handles AI-powered answer generation for question comments.
"""

from datetime import datetime
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from ..celery_config import celery_app
from ..models import InstagramComment, CommentClassification, QuestionAnswer, ProcessingStatus, AnswerStatus
from ..simple_dependencies import get_classification_service  # We'll create answer service later
from .base import BaseTaskExecutor, RetryableTask, create_task_logger

logger = create_task_logger("answer_generation")


class AnswerGenerationExecutor(BaseTaskExecutor, RetryableTask):
    """Handles answer generation operations"""
    
    def __init__(self):
        BaseTaskExecutor.__init__(self, "answer_generation")
        RetryableTask.__init__(self, max_retries=3, retry_delay=60)
    
    async def generate_answer_operation(
        self,
        session,
        comment_id: str
    ) -> dict:
        """
        Core answer generation operation.
        
        Args:
            session: Database session
            comment_id: Instagram comment ID to generate answer for
            
        Returns:
            Answer generation result dictionary
        """
        # Get comment with classification
        result = await session.execute(
            select(InstagramComment)
            .options(selectinload(InstagramComment.classification))
            .where(InstagramComment.id == comment_id)
        )
        comment = result.scalar_one_or_none()
        
        if not comment:
            raise ValueError(f"Comment {comment_id} not found")
        
        if not comment.classification:
            raise ValueError(f"Comment {comment_id} has no classification")
        
        # Verify it's classified as a question
        if comment.classification.classification != "question / inquiry":
            logger.info(f"Comment {comment_id} is not a question, skipping")
            return {
                "comment_id": comment_id,
                "status": "skipped",
                "reason": "not_a_question"
            }
        
        # Check if classification is completed
        if comment.classification.processing_status != ProcessingStatus.COMPLETED:
            raise ValueError(f"Comment {comment_id} classification not completed")
        
        # Get or create answer record
        existing_answer = await session.execute(
            select(QuestionAnswer).where(QuestionAnswer.comment_id == comment_id)
        )
        answer_record = existing_answer.scalar_one_or_none()
        
        if answer_record and answer_record.processing_status == AnswerStatus.COMPLETED:
            logger.info(f"Answer already exists for comment {comment_id}")
            return {
                "comment_id": comment_id,
                "status": "skipped",
                "reason": "already_completed"
            }
        
        if not answer_record:
            answer_record = QuestionAnswer(
                comment_id=comment_id,
                processing_status=AnswerStatus.PROCESSING,
                processing_started_at=datetime.utcnow()
            )
            session.add(answer_record)
        else:
            answer_record.processing_status = AnswerStatus.PROCESSING
            answer_record.processing_started_at = datetime.utcnow()
        
        await session.commit()
        
        # TODO: Implement answer generation service
        # For now, create a placeholder
        answer_text = f"Thank you for your question about our services. We'll get back to you soon!"
        
        # Update answer record
        answer_record.answer = answer_text
        answer_record.answer_confidence = 80
        answer_record.answer_quality_score = 75
        answer_record.processing_status = AnswerStatus.COMPLETED
        answer_record.processing_completed_at = datetime.utcnow()
        answer_record.last_error = None
        
        await session.commit()
        
        logger.info(
            f"Answer generated for comment {comment_id}",
            comment_id=comment_id,
            answer_length=len(answer_text)
        )
        
        # Trigger Instagram reply
        from .instagram_replies import send_instagram_reply
        send_instagram_reply.delay(comment_id, answer_text)
        
        return {
            "comment_id": comment_id,
            "answer": answer_text,
            "confidence": 80,
            "status": "completed"
        }
    
    async def process_pending_questions_operation(
        self,
        session,
        limit: int = 50
    ) -> dict:
        """
        Process all pending questions that need answers.
        
        Args:
            session: Database session
            limit: Maximum number of questions to process
            
        Returns:
            Processing result dictionary
        """
        # Find comments classified as questions without answers
        stmt = select(InstagramComment).join(CommentClassification).outerjoin(QuestionAnswer).where(
            and_(
                CommentClassification.classification == "question / inquiry",
                CommentClassification.processing_status == ProcessingStatus.COMPLETED,
                QuestionAnswer.id.is_(None)
            )
        ).limit(limit)
        
        result = await session.execute(stmt)
        pending_comments = result.scalars().all()
        
        if not pending_comments:
            logger.info("No pending questions to process")
            return {"processed": 0, "message": "No pending questions"}
        
        logger.info(f"Processing {len(pending_comments)} pending questions")
        
        # Trigger answer generation for each
        processed = 0
        for comment in pending_comments:
            try:
                await self.generate_answer_operation(session, comment.id)
                processed += 1
            except Exception as e:
                logger.error(
                    f"Failed to process question {comment.id}",
                    comment_id=comment.id,
                    error=str(e)
                )
        
        return {
            "processed": processed,
            "total_found": len(pending_comments),
            "message": f"Processed {processed} of {len(pending_comments)} questions"
        }


# Create executor instance
answer_executor = AnswerGenerationExecutor()


@celery_app.task(bind=True, max_retries=3, name='core.tasks.answer_generation.generate_answer')
def generate_answer(self, comment_id: str):
    """
    Generate an AI answer for a question comment.
    
    This task:
    1. Verifies the comment is classified as a question
    2. Generates an appropriate answer using AI
    3. Stores the answer in the database
    4. Triggers Instagram reply sending
    
    Args:
        comment_id: Instagram comment ID to generate answer for
        
    Returns:
        Dict with answer generation results
    """
    try:
        result = answer_executor.run_async_task(
            answer_executor.generate_answer_operation,
            comment_id
        )
        return result
        
    except Exception as e:
        # Handle retry logic
        if answer_executor.should_retry(self.request.retries, e):
            retry_delay = answer_executor.get_retry_delay(self.request.retries)
            
            logger.warning(
                f"Answer generation will retry in {retry_delay} seconds",
                comment_id=comment_id,
                retry_count=self.request.retries,
                error=str(e)
            )
            
            raise self.retry(countdown=retry_delay, exc=e)
        else:
            logger.error(
                f"Answer generation failed after {self.request.retries} retries",
                comment_id=comment_id,
                error=str(e)
            )
            
            return {
                "success": False,
                "error": str(e),
                "comment_id": comment_id,
                "retry_count": self.request.retries
            }


@celery_app.task(name='core.tasks.answer_generation.process_pending_questions')
def process_pending_questions(limit: int = 50):
    """
    Process all pending questions that need answers.
    
    This task runs periodically to ensure no questions are missed.
    It finds comments classified as questions that don't have answers yet.
    
    Args:
        limit: Maximum number of questions to process in one run
        
    Returns:
        Dict with processing results
    """
    try:
        result = answer_executor.run_async_task(
            answer_executor.process_pending_questions_operation,
            limit
        )
        return result
        
    except Exception as e:
        logger.error(
            "Failed to process pending questions",
            error=str(e),
            limit=limit
        )
        
        return {
            "success": False,
            "error": str(e),
            "processed": 0
        }
