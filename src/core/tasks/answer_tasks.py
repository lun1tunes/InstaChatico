"""Answer generation tasks - refactored using Clean Architecture."""

import logging

from ..celery_app import celery_app
from ..utils.task_helpers import async_task, get_db_session
from ..container import get_container

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
@async_task
async def generate_answer_task(self, comment_id: str):
    """Generate answer for Instagram comment question - orchestration only."""
    async with get_db_session() as session:
        container = get_container()
        use_case = container.generate_answer_use_case(session=session)
        result = await use_case.execute(comment_id, retry_count=self.request.retries)

        # Handle retry logic
        if result["status"] == "retry" and self.request.retries < self.max_retries:
            raise self.retry(countdown=10)

        # Trigger reply if answer generated successfully
        if result["status"] == "success" and result.get("answer"):
            logger.info(f"Triggering Instagram reply for comment {comment_id}")
            try:
                reply_result = celery_app.send_task(
                    "core.tasks.instagram_reply_tasks.send_instagram_reply_task", args=[comment_id, result["answer"]]
                )
                logger.info(f"Reply task queued: {reply_result.id}")
            except Exception:
                logger.exception(f"Failed to queue reply task for {comment_id}")

        return result
