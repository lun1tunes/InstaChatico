import asyncio
import logging
from datetime import datetime
from ..utils.time import now_db_utc
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import selectinload

from ..celery_app import celery_app
from ..models import CommentClassification, InstagramComment, ProcessingStatus, Media
from ..services.classification_service import CommentClassificationService
from ..services.media_service import MediaService
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

            # Ensure media data exists before classification
            logger.debug(f"Ensuring media data exists for comment {comment_id} (media_id: {comment.media_id})")
            media_service = MediaService()
            media = await media_service.get_or_create_media(comment.media_id, session)

            if not media:
                logger.error(f"Failed to get/create media {comment.media_id} for comment {comment_id}")
                # Retry the classification task after a delay
                if task_instance and task_instance.request.retries < task_instance.max_retries:
                    retry_countdown = 30  # Wait 30 seconds for media to be processed
                    logger.warning(
                        f"Retrying classification for comment {comment_id} in {retry_countdown} seconds (waiting for media data)"
                    )
                    raise task_instance.retry(countdown=retry_countdown)
                else:
                    return {"status": "error", "reason": "media_data_unavailable"}

            logger.debug(f"Media data confirmed for comment {comment_id}: {media.id}")

            # Создаем или получаем запись классификации
            if comment.classification:
                classification = comment.classification
            else:
                classification = CommentClassification(comment_id=comment_id)
                session.add(classification)

            # Обновляем статус
            classification.processing_status = ProcessingStatus.PROCESSING
            classification.processing_started_at = now_db_utc()
            classification.retry_count = task_instance.request.retries if task_instance else 0

            await session.commit()

            # Create classifier and generate conversation_id based on comment hierarchy
            classifier = CommentClassificationService()
            conversation_id = classifier._generate_conversation_id(comment.id, comment.parent_id)

            # Set conversation_id on the comment
            comment.conversation_id = conversation_id

            # Prepare media context for classification
            media_context = {
                "caption": media.caption,
                "media_type": media.media_type,
                "username": media.username,
                "comments_count": media.comments_count,
                "like_count": media.like_count,
                "permalink": media.permalink,
                "media_url": media.media_url,
                "is_comment_enabled": media.is_comment_enabled,
            }

            # Классификация with session management and media context
            classification_result = await classifier.classify_comment(comment.text, conversation_id, media_context)

            # Сохраняем результат
            classification.classification = classification_result["classification"]
            classification.confidence = classification_result["confidence"]
            classification.reasoning = classification_result["reasoning"]
            classification.llm_raw_response = classification_result["llm_raw_response"]
            classification.meta_data = {
                "contains_question": classification_result["contains_question"],
                "sentiment_score": classification_result["sentiment_score"],
                "toxicity_score": classification_result["toxicity_score"],
                "context_used": classification_result.get("context_used", False),
                "conversation_continuity": classification_result.get("conversation_continuity", False),
                "session_used": classification_result.get("session_used", False),
            }

            if classification_result.get("error"):
                classification.processing_status = ProcessingStatus.FAILED
                classification.last_error = classification_result["error"]
            else:
                classification.processing_status = ProcessingStatus.COMPLETED
                classification.processing_completed_at = now_db_utc()
                classification.last_error = None

            await session.commit()

            logger.info(f"Comment {comment_id} classified: {classification_result['classification']}")

            # Trigger answer generation if comment is classified as a question
            if classification_result["classification"].lower() == "question / inquiry":
                logger.info(f"Triggering answer generation for question {comment_id}")
                # Use direct async call that works in the same event loop
                try:
                    from core.tasks.answer_tasks import generate_answer_async

                    logger.debug(f"Imported generate_answer_async for comment {comment_id}")
                    # Run the async function directly
                    answer_result = await generate_answer_async(comment_id)
                    logger.info(f"Answer generated for question {comment_id}")
                    logger.debug(f"Answer details: {answer_result}")

                    # Trigger Instagram reply if answer was successfully generated
                    if answer_result.get("answer") and not answer_result.get("error"):
                        try:
                            logger.info(f"Queueing Instagram reply for comment {comment_id}")
                            logger.debug(f"Task args: {[comment_id, answer_result['answer']]}")
                            result = celery_app.send_task(
                                "core.tasks.instagram_reply_tasks.send_instagram_reply_task",
                                args=[comment_id, answer_result["answer"]],
                            )
                            logger.info(f"Task queued with ID: {result.id}")
                        except Exception as e:
                            logger.exception(f"Failed to queue Instagram reply for comment {comment_id}")

                except Exception:
                    logger.exception(f"Failed to generate answer for comment {comment_id}")

            # Trigger Telegram notification if comment requires attention
            # Note: "toxic / abusive" is NOT notified - we ignore such comments
            elif classification_result["classification"].lower() in [
                "urgent issue / complaint",
                "critical feedback",
                "partnership proposal",
            ]:
                classification_lower = classification_result["classification"].lower()
                notification_type_map = {
                    "urgent issue / complaint": "urgent issue",
                    "critical feedback": "critical feedback",
                    "partnership proposal": "partnership proposal",
                }
                notification_type = notification_type_map.get(classification_lower, classification_lower)
                logger.info(f"Triggering Telegram notification for {notification_type} comment {comment_id}")
                try:
                    result = celery_app.send_task(
                        "core.tasks.telegram_tasks.send_telegram_notification_task", args=[comment_id]
                    )
                    logger.info(f"Telegram notification queued for comment {comment_id} (task_id={result.id})")
                except Exception as e:
                    logger.exception(f"Failed to queue Telegram notification for comment {comment_id}")

            return {
                "status": "success",
                "comment_id": comment_id,
                "classification": classification_result["classification"],
                "confidence": classification_result["confidence"],
            }

        except Exception as exc:
            logger.exception(f"Error processing comment {comment_id}")
            await session.rollback()

            # Повторная попытка
            if task_instance and task_instance.request.retries < task_instance.max_retries:
                retry_countdown = 2**task_instance.request.retries * 60
                raise task_instance.retry(countdown=retry_countdown, exc=exc)

            # Если превышено количество попыток
            try:
                if "classification" in locals() and classification:
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
                select(InstagramComment)
                .join(CommentClassification)
                .where(
                    and_(
                        CommentClassification.processing_status == ProcessingStatus.RETRY,
                        CommentClassification.retry_count < CommentClassification.max_retries,
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
