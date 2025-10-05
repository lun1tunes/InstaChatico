"""Classification tasks - refactored using Clean Architecture."""

import logging
from sqlalchemy import select, and_

from ..celery_app import celery_app
from ..models import CommentClassification, InstagramComment, ProcessingStatus
from ..use_cases.classify_comment import ClassifyCommentUseCase
from ..utils.task_helpers import async_task, get_db_session

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
@async_task
async def classify_comment_task(self, comment_id: str):
    """Classify Instagram comment using AI - orchestration only."""
    async with get_db_session() as session:
        use_case = ClassifyCommentUseCase(session)
        result = await use_case.execute(comment_id, retry_count=self.request.retries)

        # Handle retry logic
        if result["status"] == "retry" and self.request.retries < self.max_retries:
            raise self.retry(countdown=10)

        # Trigger post-classification actions
        if result["status"] == "success":
            await _trigger_post_classification_actions(result)

        return result


async def _trigger_post_classification_actions(classification_result: dict):
    """Trigger follow-up actions based on classification."""
    comment_id = classification_result["comment_id"]
    classification = classification_result.get("classification", "").lower()

    # Answer generation for questions
    if classification == "question / inquiry":
        logger.info(f"Triggering answer generation for question {comment_id}")
        try:
            from .answer_tasks import generate_answer_task
            result = generate_answer_task.delay(comment_id)
            logger.info(f"Answer task queued: {result.id}")
        except Exception:
            logger.exception(f"Failed to queue answer task for {comment_id}")

    # Hide toxic/complaint comments
    if classification in ["urgent issue / complaint", "toxic / abusive"]:
        logger.info(f"Triggering hide for {classification} comment {comment_id}")
        try:
            result = celery_app.send_task(
                "core.tasks.instagram_reply_tasks.hide_instagram_comment_task",
                args=[comment_id]
            )
            logger.info(f"Hide task queued: {result.id}")
        except Exception:
            logger.exception(f"Failed to queue hide task for {comment_id}")

    # Telegram notifications (excluding toxic)
    if classification in ["urgent issue / complaint", "critical feedback", "partnership proposal"]:
        logger.info(f"Triggering Telegram notification for {classification} comment {comment_id}")
        try:
            result = celery_app.send_task(
                "core.tasks.telegram_tasks.send_telegram_notification_task",
                args=[comment_id]
            )
            logger.info(f"Telegram task queued: {result.id}")
        except Exception:
            logger.exception(f"Failed to queue Telegram task for {comment_id}")


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
