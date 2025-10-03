import logging
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from ..celery_app import celery_app
from ..models import CommentClassification, InstagramComment, ProcessingStatus, Media
from ..services.classification_service import CommentClassificationService
from ..services.media_service import MediaService
from ..utils.time import now_db_utc
from ..utils.task_helpers import async_task, get_db_session, retry_with_backoff

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
@async_task
async def classify_comment_task(self, comment_id: str):
    """Classify Instagram comment using AI."""
    return await classify_comment_async(comment_id, self)


async def classify_comment_async(comment_id: str, task_instance=None):
    """Async comment classification task."""
    async with get_db_session() as session:
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
            media_service = MediaService()
            media = await media_service.get_or_create_media(comment.media_id, session)

            if not media:
                logger.error(f"Failed to get/create media {comment.media_id} for comment {comment_id}")
                if task_instance and task_instance.request.retries < task_instance.max_retries:
                    logger.warning(f"Retrying classification for comment {comment_id} in 30s (waiting for media)")
                    raise task_instance.retry(countdown=30)
                return {"status": "error", "reason": "media_data_unavailable"}

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
                "media_context": media.media_context,  # AI-analyzed image description
                "username": media.username,
                "comments_count": media.comments_count,
                "like_count": media.like_count,
                "permalink": media.permalink,
                "media_url": media.media_url,
                "is_comment_enabled": media.is_comment_enabled,
            }

            # Классификация with session management and media context
            classification_result = await classifier.classify_comment(
                comment.text, conversation_id, media_context, username=comment.username
            )

            # Сохраняем результат (classification_result is now a Pydantic model)
            classification.classification = classification_result.classification
            classification.confidence = classification_result.confidence
            classification.reasoning = classification_result.reasoning
            classification.input_tokens = classification_result.input_tokens
            classification.output_tokens = classification_result.output_tokens
            classification.meta_data = {}

            if classification_result.error:
                classification.processing_status = ProcessingStatus.FAILED
                classification.last_error = classification_result.error
            else:
                classification.processing_status = ProcessingStatus.COMPLETED
                classification.processing_completed_at = now_db_utc()
                classification.last_error = None

            await session.commit()

            logger.info(f"Comment {comment_id} classified: {classification_result.classification}")

            # Trigger answer generation if comment is classified as a question
            if classification_result.classification and classification_result.classification.lower() == "question / inquiry":
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
                    if answer_result.get("answer") and answer_result.get("status") == "success":
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
            elif classification_result.classification and classification_result.classification.lower() in [
                "urgent issue / complaint",
                "critical feedback",
                "partnership proposal",
            ]:
                classification_lower = classification_result.classification.lower()
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
                "classification": classification_result.classification,
                "confidence": classification_result.confidence,
            }

        except Exception as exc:
            logger.exception(f"Error processing comment {comment_id}")
            await session.rollback()
            return retry_with_backoff(task_instance, exc)


@celery_app.task
@async_task
async def retry_failed_classifications():
    """Retry failed classifications."""
    return await retry_failed_classifications_async()


async def retry_failed_classifications_async():
    """Async retry failed classifications."""
    async with get_db_session() as session:
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
