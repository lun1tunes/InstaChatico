"""Classification tasks - refactored using Clean Architecture."""

import logging

from ..celery_app import celery_app
from ..utils.task_helpers import async_task, get_db_session
from ..container import get_container

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
@async_task
async def classify_comment_task(self, comment_id: str):
    """Classify Instagram comment using AI - orchestration only."""
    async with get_db_session() as session:
        container = get_container()
        use_case = container.classify_comment_use_case(session=session)
        result = await use_case.execute(comment_id, retry_count=self.request.retries)

        # Handle retry logic
        if result["status"] == "retry" and self.request.retries < self.max_retries:
            raise self.retry(countdown=10)

        # Trigger post-classification actions
        if result["status"] == "success":
            await _trigger_post_classification_actions(result)

        return result


async def _trigger_post_classification_actions(classification_result: dict):
    """
    Trigger follow-up actions based on classification.

    Uses DI container to get task queue - follows SOLID principles.
    """
    comment_id = classification_result["comment_id"]
    classification = classification_result.get("classification", "").lower()

    # Get task queue from container
    container = get_container()
    task_queue = container.task_queue()

    # Answer generation for questions
    if classification == "question / inquiry":
        logger.info(f"Triggering answer generation for question {comment_id}")
        try:
            task_id = task_queue.enqueue(
                "core.tasks.answer_tasks.generate_answer_task",
                comment_id,
            )
            logger.info(f"Answer task queued: {task_id}")
        except Exception:
            logger.exception(f"Failed to queue answer task for {comment_id}")

    # Hide toxic/complaint comments
    if classification in ["urgent issue / complaint", "toxic / abusive"]:
        logger.info(f"Triggering hide for {classification} comment {comment_id}")
        try:
            task_id = task_queue.enqueue(
                "core.tasks.instagram_reply_tasks.hide_instagram_comment_task",
                comment_id,
            )
            logger.info(f"Hide task queued: {task_id}")
        except Exception:
            logger.exception(f"Failed to queue hide task for {comment_id}")

    # Telegram notifications (excluding toxic)
    if classification in ["urgent issue / complaint", "critical feedback", "partnership proposal"]:
        logger.info(f"Triggering Telegram notification for {classification} comment {comment_id}")
        try:
            task_id = task_queue.enqueue(
                "core.tasks.telegram_tasks.send_telegram_notification_task",
                comment_id,
            )
            logger.info(f"Telegram task queued: {task_id}")
        except Exception:
            logger.exception(f"Failed to queue Telegram task for {comment_id}")


@celery_app.task
@async_task
async def retry_failed_classifications():
    """Retry failed classifications."""
    return await retry_failed_classifications_async()


async def retry_failed_classifications_async():
    """
    Async retry failed classifications.

    Uses DI container to get task queue - follows SOLID principles.
    """
    from ..repositories.classification import ClassificationRepository

    async with get_db_session() as session:
        try:
            # Get task queue from container
            container = get_container()
            task_queue = container.task_queue()

            # Use repository instead of direct SQL
            classification_repo = ClassificationRepository(session)
            retry_classifications = await classification_repo.get_pending_retries()

            for classification in retry_classifications:
                task_queue.enqueue(
                    "core.tasks.classification_tasks.classify_comment_task",
                    classification.comment_id,
                )

            logger.info(f"Queued {len(retry_classifications)} comments for retry")
            return {"retried_count": len(retry_classifications)}
        except Exception as e:
            logger.error(f"Error in retry task: {e}")
            return {"error": str(e)}
