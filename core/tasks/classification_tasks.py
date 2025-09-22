import asyncio
import logging
from datetime import datetime
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import selectinload

from ..celery_app import celery_app
from ..models import CommentClassification, InstagramComment, ProcessingStatus
from ..services.classification_service import CommentClassificationService
from ..config import settings

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, max_retries=3)
def classify_comment_task(self, comment_id: str):
    """Синхронная обертка для асинхронной задачи классификации"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(classify_comment_async(comment_id, self))
    finally:
        loop.close()

async def classify_comment_async(comment_id: str, task_instance=None):
    """Асинхронная задача классификации комментария"""
    # Create a fresh engine and session for this task
    engine = create_async_engine(settings.db.url, echo=settings.db.echo)
    session_factory = async_sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    
    async with session_factory() as session:
        try:
            # Получаем комментарий
            result = await session.execute(
                select(InstagramComment)
                .options(selectinload(InstagramComment.classification))
                .where(InstagramComment.id == comment_id)
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
            classification.meta_data = {
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
                if 'classification' in locals() and classification:
                    classification.processing_status = ProcessingStatus.FAILED
                    classification.last_error = str(exc)
                    await session.commit()
            except Exception:
                pass
            
            return {"status": "error", "reason": str(exc)}
        finally:
            await engine.dispose()

@celery_app.task
def retry_failed_classifications():
    """Повторная обработка неудачных классификаций"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(retry_failed_classifications_async())
    finally:
        loop.close()

async def retry_failed_classifications_async():
    """Асинхронная обработка повторных попыток"""
    # Create a fresh engine and session for this task
    engine = create_async_engine(settings.db.url, echo=settings.db.echo)
    session_factory = async_sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    
    async with session_factory() as session:
        try:
            # Находим комментарии для повторной обработки
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
            await engine.dispose()