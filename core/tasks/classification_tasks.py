import asyncio
import logging
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..celery_app import celery_app
from ..models import CommentClassification, InstagramComment, ProcessingStatus, db_helper
from ..services.classification_service import CommentClassificationService
from ..config import settings

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, max_retries=3)
def classify_comment_task(self, comment_id: str):
    """Синхронная обертка для асинхронной задачи классификации"""
    return asyncio.get_event_loop().run_until_complete(
        classify_comment_async(comment_id, self)
    )

async def classify_comment_async(comment_id: str, task_instance=None):
    """Асинхронная задача классификации комментария"""
    session: AsyncSession = db_helper.get_scoped_session()
    
    try:
        # Получаем комментарий
        result = await session.execute(
            select(InstagramComment).where(InstagramComment.id == comment_id)
        )
        comment = result.scalar_one_or_none()
        
        if not comment:
            logger.warning(f"Comment {comment_id} not found")
            return {"status": "error", "reason": "comment_not_found"}
        
        # Создаем или получаем запись классификации
        if comment.classification:
            classification = comment.classification
        else:
            classification = CommentClassification(comment_id=comment_id)
            session.add(classification)
        
        # Обновляем статус
        classification.processing_status = ProcessingStatus.PROCESSING
        classification.processing_started_at = datetime.utcnow()
        classification.retry_count = task_instance.request.retries if task_instance else 0
        
        await session.commit()
        
        # Классификация
        classifier = CommentClassificationService()
        classification_result = await classifier.classify_comment(comment.text)
        
        # Сохраняем результат
        classification.classification = classification_result['classification']
        classification.confidence = classification_result['confidence']
        classification.llm_raw_response = classification_result['llm_raw_response']
        classification.metadata = {
            'contains_question': classification_result['contains_question'],
            'sentiment_score': classification_result['sentiment_score'],
            'toxicity_score': classification_result['toxicity_score']
        }
        
        if classification_result.get('error'):
            classification.processing_status = ProcessingStatus.FAILED
            classification.last_error = classification_result['error']
        else:
            classification.processing_status = ProcessingStatus.COMPLETED
            classification.processing_completed_at = datetime.utcnow()
            classification.last_error = None
        
        await session.commit()
        
        logger.info(f"Comment {comment_id} classified as {classification_result['classification']}")
        
        return {
            "status": "success",
            "comment_id": comment_id,
            "classification": classification_result['classification'],
            "confidence": classification_result['confidence']
        }
        
    except Exception as exc:
        logger.error(f"Error processing comment {comment_id}: {exc}")
        await session.rollback()
        
        # Повторная попытка
        if task_instance and task_instance.request.retries < task_instance.max_retries:
            retry_countdown = 2 ** task_instance.request.retries * 60
            raise task_instance.retry(countdown=retry_countdown, exc=exc)
        
        # Если превышено количество попыток
        try:
            classification.processing_status = ProcessingStatus.FAILED
            classification.last_error = str(exc)
            await session.commit()
        except:
            pass
        
        return {"status": "error", "reason": str(exc)}
    
    finally:
        await session.close()

@celery_app.task
def retry_failed_classifications():
    """Повторная обработка неудачных классификаций"""
    return asyncio.get_event_loop().run_until_complete(
        retry_failed_classifications_async()
    )

async def retry_failed_classifications_async():
    """Асинхронная обработка повторных попыток"""
    session: AsyncSession = db_helper.get_scoped_session()
    
    try:
        # Находим комментарии для повторной обработки
        from sqlalchemy import and_
        result = await session.execute(
            select(InstagramComment).join(CommentClassification).where(
                and_(
                    CommentClassification.processing_status == ProcessingStatus.RETRY,
                    CommentClassification.retry_count < CommentClassification.max_retries
                )
            )
        )
        retry_comments = result.scalars().all()
        
        for comment in retry_comments:
            classify_comment_task.delay(comment.id)
        
        logger.info(f"Queued {len(retry_comments)} comments for retry")
        return {"retried_count": len(retry_comments)}
    
    except Exception as e:
        logger.error(f"Error in retry task: {e}")
        return {"error": str(e)}
    
    finally:
        await session.close()