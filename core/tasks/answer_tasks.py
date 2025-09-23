import asyncio
import logging
from datetime import datetime
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import selectinload

from celery import Celery
from ..config import settings

# Create a separate celery app instance to avoid circular imports
celery_app = Celery(
    'instagram_classifier',
    broker=settings.celery.broker_url,
    backend=settings.celery.result_backend,
)

from ..models import QuestionAnswer, CommentClassification, InstagramComment, AnswerStatus, ProcessingStatus
from ..services.answer_service import QuestionAnswerService

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, max_retries=3)
def generate_answer_task(self, comment_id: str):
    """Синхронная обертка для асинхронной задачи генерации ответа"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(generate_answer_async(comment_id, self))
    finally:
        loop.close()

async def generate_answer_async(comment_id: str, task_instance=None):
    """Асинхронная задача генерации ответа на вопрос"""
    # Create a fresh engine and session for this task
    engine = create_async_engine(settings.db.url, echo=settings.db.echo)
    session_factory = async_sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    
    async with session_factory() as session:
        try:
            # Получаем комментарий с классификацией
            result = await session.execute(
                select(InstagramComment)
                .options(selectinload(InstagramComment.classification))
                .where(InstagramComment.id == comment_id)
            )
            comment = result.scalar_one_or_none()
            
            if not comment:
                logger.warning(f"Comment {comment_id} not found")
                return {"status": "error", "reason": "comment_not_found"}
            
            if not comment.classification:
                logger.warning(f"Comment {comment_id} has no classification")
                return {"status": "error", "reason": "no_classification"}
            
            # Проверяем, что комментарий классифицирован как вопрос
            if comment.classification.classification.lower() != "question / inquiry":
                logger.info(f"Comment {comment_id} is not a question, skipping answer generation")
                return {"status": "skipped", "reason": "not_a_question"}
            
            # Проверяем, что классификация завершена
            if comment.classification.processing_status != ProcessingStatus.COMPLETED:
                logger.warning(f"Comment {comment_id} classification not completed yet")
                return {"status": "error", "reason": "classification_not_completed"}
            
            # Создаем или получаем запись ответа
            existing_answer = await session.execute(
                select(QuestionAnswer).where(QuestionAnswer.comment_id == comment_id)
            )
            answer_record = existing_answer.scalar_one_or_none()
            
            if answer_record:
                # Если уже есть запись, проверяем статус
                if answer_record.processing_status == AnswerStatus.COMPLETED:
                    logger.info(f"Answer for comment {comment_id} already exists and completed")
                    return {"status": "skipped", "reason": "already_completed"}
                
                # Если в процессе или ошибка, обновляем статус
                answer_record.processing_status = AnswerStatus.PROCESSING
                answer_record.processing_started_at = datetime.utcnow()
                answer_record.retry_count = task_instance.request.retries if task_instance else 0
            else:
                # Создаем новую запись
                answer_record = QuestionAnswer(
                    comment_id=comment_id,
                    processing_status=AnswerStatus.PROCESSING,
                    processing_started_at=datetime.utcnow(),
                    retry_count=task_instance.request.retries if task_instance else 0
                )
                session.add(answer_record)
            
            await session.commit()
            
            # Генерируем ответ
            answer_service = QuestionAnswerService()
            answer_result = await answer_service.generate_answer(comment.text)
            
            # Сохраняем результат
            if answer_result.get('error'):
                answer_record.processing_status = AnswerStatus.FAILED
                answer_record.last_error = answer_result['error']
            else:
                answer_record.answer = answer_result['answer']
                answer_record.answer_confidence = answer_result['confidence']
                answer_record.answer_quality_score = answer_result['quality_score']
                answer_record.llm_raw_response = answer_result.get('llm_raw_response', '')
                answer_record.tokens_used = answer_result.get('tokens_used', 0)
                answer_record.processing_time_ms = answer_result.get('processing_time_ms', 0)
                answer_record.meta_data = answer_result.get('meta_data', {})
                
                answer_record.processing_status = AnswerStatus.COMPLETED
                answer_record.processing_completed_at = datetime.utcnow()
                answer_record.last_error = None
            
            await session.commit()
            
            logger.info(f"Answer generated for comment {comment_id}: {answer_result.get('answer', 'ERROR')[:100]}...")
            
            # Trigger Instagram reply if answer was successfully generated
            if answer_result.get('answer') and not answer_result.get('error'):
                try:
                    from .instagram_reply_tasks import send_instagram_reply_task
                    logger.info(f"Triggering Instagram reply for comment {comment_id}")
                    send_instagram_reply_task.delay(comment_id, answer_result['answer'])
                except Exception as e:
                    logger.error(f"Failed to trigger Instagram reply for comment {comment_id}: {e}")
            
            return {
                "status": "success",
                "comment_id": comment_id,
                "answer": answer_result.get('answer'),
                "confidence": answer_result.get('confidence'),
                "quality_score": answer_result.get('quality_score')
            }
            
        except Exception as exc:
            logger.error(f"Error processing answer for comment {comment_id}: {exc}")
            await session.rollback()
            
            # Повторная попытка
            if task_instance and task_instance.request.retries < task_instance.max_retries:
                retry_countdown = 2 ** task_instance.request.retries * 60
                raise task_instance.retry(countdown=retry_countdown, exc=exc)
            
            # Если превышено количество попыток
            try:
                if 'answer_record' in locals() and answer_record:
                    answer_record.processing_status = AnswerStatus.FAILED
                    answer_record.last_error = str(exc)
                    await session.commit()
            except Exception:
                pass
            
            return {"status": "error", "reason": str(exc)}
        finally:
            await engine.dispose()

@celery_app.task
def retry_failed_answers():
    """Периодическая задача для повторной обработки неудачных ответов"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(retry_failed_answers_async())
    finally:
        loop.close()

async def retry_failed_answers_async():
    """Асинхронная функция для повторной обработки неудачных ответов"""
    engine = create_async_engine(settings.db.url, echo=settings.db.echo)
    session_factory = async_sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    
    async with session_factory() as session:
        try:
            # Находим записи с ошибками, которые можно повторить
            result = await session.execute(
                select(QuestionAnswer)
                .where(
                    and_(
                        QuestionAnswer.processing_status == AnswerStatus.FAILED,
                        QuestionAnswer.retry_count < QuestionAnswer.max_retries
                    )
                )
            )
            failed_answers = result.scalars().all()
            
            retry_count = 0
            for answer_record in failed_answers:
                logger.info(f"Retrying answer generation for comment {answer_record.comment_id}")
                generate_answer_task.delay(answer_record.comment_id)
                retry_count += 1
            
            logger.info(f"Queued {retry_count} failed answers for retry")
            
        except Exception as exc:
            logger.error(f"Error in retry_failed_answers: {exc}")
        finally:
            await engine.dispose()

@celery_app.task(bind=True, max_retries=3)
def process_pending_questions_task(self):
    """Периодическая задача для обработки всех ожидающих вопросов."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(process_pending_questions_async(self))
    finally:
        loop.close()

async def process_pending_questions_async(task_instance=None):
    engine = create_async_engine(settings.db.url, echo=settings.db.echo)
    session_factory = async_sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    async with session_factory() as session:
        try:
            # Find comments classified as questions that don't have answers
            stmt = select(InstagramComment).join(CommentClassification).outerjoin(QuestionAnswer).where(
                and_(
                    CommentClassification.classification == "question / inquiry",
                    CommentClassification.processing_status == ProcessingStatus.COMPLETED,
                    QuestionAnswer.id.is_(None)
                )
            )
            result = await session.execute(stmt)
            pending_comments = result.scalars().all()

            if not pending_comments:
                logger.info("No pending questions to process.")
                return {"status": "success", "message": "No pending questions to process"}

            logger.info(f"Processing {len(pending_comments)} pending questions.")
            processed_count = 0
            results = []

            for comment in pending_comments:
                try:
                    answer_result = await generate_answer_async(comment.id)
                    results.append({"comment_id": comment.id, "status": "success", "result": answer_result})
                    processed_count += 1
                    logger.info(f"Processed question comment {comment.id}")
                except Exception as e:
                    results.append({"comment_id": comment.id, "status": "error", "error": str(e)})
                    logger.error(f"Failed to process question comment {comment.id}: {e}")

            return {"status": "success", "processed_count": processed_count, "total_found": len(pending_comments), "results": results}

        except Exception as e:
            logger.error(f"Error in process_pending_questions: {e}")
            await session.rollback()
            return {"status": "error", "reason": str(e)}
        finally:
            await engine.dispose()
