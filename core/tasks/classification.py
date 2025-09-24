"""
Comment classification tasks for InstaChatico.
Handles AI-powered classification of Instagram comments.
"""

from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..celery_config import celery_app
from ..models import InstagramComment, CommentClassification, ProcessingStatus
from ..simple_dependencies import get_classification_service
from .base import BaseTaskExecutor, RetryableTask, create_task_logger

logger = create_task_logger("classification")


class CommentClassificationExecutor(BaseTaskExecutor, RetryableTask):
    """Handles comment classification operations"""
    
    def __init__(self):
        BaseTaskExecutor.__init__(self, "classification")
        RetryableTask.__init__(self, max_retries=3, retry_delay=60)
    
    async def classify_comment_operation(
        self,
        session,
        comment_id: str
    ) -> dict:
        """
        Core classification operation.
        
        Args:
            session: Database session
            comment_id: Instagram comment ID to classify
            
        Returns:
            Classification result dictionary
        """
        # Get comment with classification
        result = await session.execute(
            select(InstagramComment)
            .options(selectinload(InstagramComment.classification))
            .where(InstagramComment.id == comment_id)
        )
        comment = result.scalar_one_or_none()
        
        if not comment:
            logger.warning(f"Comment {comment_id} not found")
            raise ValueError(f"Comment {comment_id} not found")
        
        # Get or create classification record
        if comment.classification:
            classification = comment.classification
        else:
            classification = CommentClassification(comment_id=comment_id)
            session.add(classification)
        
        # Update status to processing
        classification.processing_status = ProcessingStatus.PROCESSING
        classification.processing_started_at = datetime.utcnow()
        await session.commit()
        
        # Perform AI classification
        classification_service = get_classification_service()
        classification_result = await classification_service.classify_comment(comment.text)
        
        # Update classification with results
        if classification_result.get('error'):
            classification.processing_status = ProcessingStatus.FAILED
            classification.last_error = classification_result['error']
        else:
            classification.classification = classification_result['classification']
            classification.confidence = classification_result['confidence']
            classification.llm_raw_response = classification_result.get('llm_raw_response')
            classification.meta_data = {
                'contains_question': classification_result.get('contains_question'),
                'sentiment_score': classification_result.get('sentiment_score'),
                'toxicity_score': classification_result.get('toxicity_score')
            }
            classification.processing_status = ProcessingStatus.COMPLETED
            classification.processing_completed_at = datetime.utcnow()
            classification.last_error = None
        
        await session.commit()
        
        logger.info(
            f"Comment {comment_id} classified as {classification_result.get('classification')}",
            comment_id=comment_id,
            classification=classification_result.get('classification'),
            confidence=classification_result.get('confidence')
        )
        
        return {
            "comment_id": comment_id,
            "classification": classification_result.get('classification'),
            "confidence": classification_result.get('confidence'),
            "status": "completed" if not classification_result.get('error') else "failed"
        }


# Create executor instance
classification_executor = CommentClassificationExecutor()


@celery_app.task(bind=True, max_retries=3, name='core.tasks.classification.classify_comment')
def classify_comment(self, comment_id: str):
    """
    Classify an Instagram comment using AI.
    
    This task:
    1. Retrieves the comment from database
    2. Sends comment text to OpenAI for classification
    3. Stores classification results in database
    4. Handles errors and retries automatically
    
    Args:
        comment_id: Instagram comment ID to classify
        
    Returns:
        Dict with classification results and status
    """
    try:
        result = classification_executor.run_async_task(
            classification_executor.classify_comment_operation,
            comment_id
        )
        
        # If classification indicates this is a question, trigger answer generation
        if (result.get("success") and 
            result.get("data", {}).get("classification") == "question / inquiry"):
            
            logger.info(f"Triggering answer generation for question: {comment_id}")
            # Import here to avoid circular imports
            from .answer_generation import generate_answer
            generate_answer.delay(comment_id)
        
        return result
        
    except Exception as e:
        # Handle retry logic
        if classification_executor.should_retry(self.request.retries, e):
            retry_delay = classification_executor.get_retry_delay(self.request.retries)
            
            logger.warning(
                f"Classification task will retry in {retry_delay} seconds",
                comment_id=comment_id,
                retry_count=self.request.retries,
                error=str(e)
            )
            
            raise self.retry(countdown=retry_delay, exc=e)
        else:
            logger.error(
                f"Classification task failed after {self.request.retries} retries",
                comment_id=comment_id,
                error=str(e)
            )
            
            return {
                "success": False,
                "error": str(e),
                "comment_id": comment_id,
                "retry_count": self.request.retries
            }


@celery_app.task(name='core.tasks.classification.batch_classify')
def batch_classify_comments(comment_ids: list[str], max_concurrent: int = 5):
    """
    Classify multiple comments concurrently.
    
    Args:
        comment_ids: List of comment IDs to classify
        max_concurrent: Maximum concurrent classifications
        
    Returns:
        Dict with batch processing results
    """
    logger.info(
        f"Starting batch classification of {len(comment_ids)} comments",
        extra_fields={"batch_size": len(comment_ids)}
    )
    
    # Trigger individual classification tasks
    results = []
    for comment_id in comment_ids:
        task_result = classify_comment.delay(comment_id)
        results.append({
            "comment_id": comment_id,
            "task_id": task_result.id
        })
    
    return {
        "success": True,
        "batch_size": len(comment_ids),
        "tasks_created": len(results),
        "task_details": results
    }
