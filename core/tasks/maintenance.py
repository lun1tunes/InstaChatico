"""
Maintenance tasks for InstaChatico.
Handles background cleanup, retry operations, and system maintenance.
"""

from datetime import datetime, timedelta
from sqlalchemy import select, and_, delete, func

from ..celery_config import celery_app
from ..models import CommentClassification, QuestionAnswer, ProcessingStatus, AnswerStatus
from .base import BaseTaskExecutor, create_task_logger

logger = create_task_logger("maintenance")


class MaintenanceExecutor(BaseTaskExecutor):
    """Handles maintenance and cleanup operations"""
    
    def __init__(self):
        BaseTaskExecutor.__init__(self, "maintenance")
    
    async def retry_failed_classifications_operation(
        self,
        session,
        max_retry_count: int = 3
    ) -> dict:
        """
        Retry failed classifications that haven't exceeded max retries.
        
        Args:
            session: Database session
            max_retry_count: Maximum retry count to consider
            
        Returns:
            Retry operation result dictionary
        """
        # Find failed classifications eligible for retry
        stmt = select(CommentClassification).where(
            and_(
                CommentClassification.processing_status == ProcessingStatus.FAILED,
                CommentClassification.retry_count < max_retry_count
            )
        )
        
        result = await session.execute(stmt)
        failed_classifications = result.scalars().all()
        
        if not failed_classifications:
            logger.info("No failed classifications to retry")
            return {"retried": 0, "message": "No failed classifications found"}
        
        logger.info(f"Retrying {len(failed_classifications)} failed classifications")
        
        # Trigger retry for each
        from .classification import classify_comment
        
        retried = 0
        for classification in failed_classifications:
            try:
                # Reset status to pending for retry
                classification.processing_status = ProcessingStatus.PENDING
                classification.retry_count += 1
                classification.last_error = None
                await session.commit()
                
                # Trigger classification task
                classify_comment.delay(classification.comment_id)
                retried += 1
                
            except Exception as e:
                logger.error(
                    f"Failed to retry classification {classification.comment_id}",
                    comment_id=classification.comment_id,
                    error=str(e)
                )
        
        return {
            "retried": retried,
            "total_found": len(failed_classifications),
            "message": f"Retried {retried} of {len(failed_classifications)} classifications"
        }
    
    async def retry_failed_answers_operation(
        self,
        session,
        max_retry_count: int = 3
    ) -> dict:
        """
        Retry failed answer generation that hasn't exceeded max retries.
        
        Args:
            session: Database session
            max_retry_count: Maximum retry count to consider
            
        Returns:
            Retry operation result dictionary
        """
        # Find failed answers eligible for retry
        stmt = select(QuestionAnswer).where(
            and_(
                QuestionAnswer.processing_status == AnswerStatus.FAILED,
                QuestionAnswer.retry_count < max_retry_count
            )
        )
        
        result = await session.execute(stmt)
        failed_answers = result.scalars().all()
        
        if not failed_answers:
            logger.info("No failed answers to retry")
            return {"retried": 0, "message": "No failed answers found"}
        
        logger.info(f"Retrying {len(failed_answers)} failed answers")
        
        # Trigger retry for each
        from .answer_generation import generate_answer
        
        retried = 0
        for answer in failed_answers:
            try:
                # Reset status to pending for retry
                answer.processing_status = AnswerStatus.PENDING
                answer.retry_count += 1
                answer.last_error = None
                await session.commit()
                
                # Trigger answer generation task
                generate_answer.delay(answer.comment_id)
                retried += 1
                
            except Exception as e:
                logger.error(
                    f"Failed to retry answer generation {answer.comment_id}",
                    comment_id=answer.comment_id,
                    error=str(e)
                )
        
        return {
            "retried": retried,
            "total_found": len(failed_answers),
            "message": f"Retried {retried} of {len(failed_answers)} answers"
        }
    
    async def cleanup_old_records_operation(
        self,
        session,
        days_old: int = 30
    ) -> dict:
        """
        Clean up old completed records to maintain database performance.
        
        Args:
            session: Database session
            days_old: Age threshold for cleanup (in days)
            
        Returns:
            Cleanup operation result dictionary
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        
        # Count records to be cleaned up
        classification_count = await session.execute(
            select(func.count(CommentClassification.id)).where(
                and_(
                    CommentClassification.processing_status == ProcessingStatus.COMPLETED,
                    CommentClassification.processing_completed_at < cutoff_date
                )
            )
        )
        
        answer_count = await session.execute(
            select(func.count(QuestionAnswer.id)).where(
                and_(
                    QuestionAnswer.processing_status == AnswerStatus.COMPLETED,
                    QuestionAnswer.processing_completed_at < cutoff_date,
                    QuestionAnswer.reply_sent == True
                )
            )
        )
        
        classifications_to_clean = classification_count.scalar()
        answers_to_clean = answer_count.scalar()
        
        if classifications_to_clean == 0 and answers_to_clean == 0:
            logger.info("No old records to clean up")
            return {"cleaned": 0, "message": "No old records found"}
        
        logger.info(
            f"Cleaning up {classifications_to_clean} classifications and {answers_to_clean} answers",
            extra_fields={
                "cutoff_date": cutoff_date.isoformat(),
                "days_old": days_old
            }
        )
        
        # Note: In production, you might want to archive instead of delete
        # For now, we'll just log what would be cleaned
        
        return {
            "cleaned": 0,  # Set to 0 for safety - implement actual cleanup if needed
            "would_clean": {
                "classifications": classifications_to_clean,
                "answers": answers_to_clean
            },
            "message": f"Would clean {classifications_to_clean + answers_to_clean} old records"
        }


# Create executor instance
maintenance_executor = MaintenanceExecutor()


@celery_app.task(name='core.tasks.maintenance.retry_failed_classifications')
def retry_failed_classifications(max_retry_count: int = 3):
    """
    Retry failed comment classifications.
    
    This task runs periodically to retry classifications that failed
    due to temporary issues (network problems, API rate limits, etc.).
    
    Args:
        max_retry_count: Maximum number of retries to attempt
        
    Returns:
        Dict with retry results
    """
    try:
        result = maintenance_executor.run_async_task(
            maintenance_executor.retry_failed_classifications_operation,
            max_retry_count
        )
        return result
        
    except Exception as e:
        logger.error(
            "Failed to retry failed classifications",
            error=str(e),
            max_retry_count=max_retry_count
        )
        
        return {
            "success": False,
            "error": str(e),
            "retried": 0
        }


@celery_app.task(name='core.tasks.maintenance.retry_failed_answers')
def retry_failed_answers(max_retry_count: int = 3):
    """
    Retry failed answer generation.
    
    This task runs periodically to retry answer generation that failed
    due to temporary issues with the AI service.
    
    Args:
        max_retry_count: Maximum number of retries to attempt
        
    Returns:
        Dict with retry results
    """
    try:
        result = maintenance_executor.run_async_task(
            maintenance_executor.retry_failed_answers_operation,
            max_retry_count
        )
        return result
        
    except Exception as e:
        logger.error(
            "Failed to retry failed answers",
            error=str(e),
            max_retry_count=max_retry_count
        )
        
        return {
            "success": False,
            "error": str(e),
            "retried": 0
        }


@celery_app.task(name='core.tasks.maintenance.cleanup_old_records')
def cleanup_old_records(days_old: int = 30):
    """
    Clean up old completed records to maintain database performance.
    
    This task runs daily to remove old completed records that are
    no longer needed for operational purposes.
    
    Args:
        days_old: Age threshold for cleanup (in days)
        
    Returns:
        Dict with cleanup results
    """
    try:
        result = maintenance_executor.run_async_task(
            maintenance_executor.cleanup_old_records_operation,
            days_old
        )
        return result
        
    except Exception as e:
        logger.error(
            "Failed to cleanup old records",
            error=str(e),
            days_old=days_old
        )
        
        return {
            "success": False,
            "error": str(e),
            "cleaned": 0
        }


@celery_app.task(name='core.tasks.maintenance.health_check')
def celery_health_check():
    """
    Health check task for monitoring Celery worker status.
    
    This task can be called to verify that Celery workers are
    functioning properly and can process tasks.
    
    Returns:
        Dict with health status
    """
    try:
        logger.info("Celery health check executed")
        
        return {
            "success": True,
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "worker_id": celery_app.control.inspect().active_queues(),
            "message": "Celery worker is healthy and processing tasks"
        }
        
    except Exception as e:
        logger.error(
            "Celery health check failed",
            error=str(e)
        )
        
        return {
            "success": False,
            "status": "unhealthy", 
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
