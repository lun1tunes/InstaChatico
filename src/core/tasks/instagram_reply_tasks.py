"""Instagram reply and hide tasks - refactored using Clean Architecture."""

import logging

from ..celery_app import celery_app
from ..use_cases.send_reply import SendReplyUseCase
from ..use_cases.hide_comment import HideCommentUseCase
from ..utils.task_helpers import async_task, get_db_session
from ..utils.lock_manager import LockManager
from ..config import settings
from ..container import get_container

logger = logging.getLogger(__name__)

# Initialize lock manager
lock_manager = LockManager(settings.celery.broker_url)


@celery_app.task(bind=True, max_retries=3)
@async_task
async def send_instagram_reply_task(self, comment_id: str, answer_text: str = None):
    """Send Instagram reply - orchestration only."""
    async with lock_manager.acquire(f"instagram_reply_lock:{comment_id}") as acquired:
        if not acquired:
            logger.info(f"Reply for {comment_id} already processing")
            return {"status": "skipped", "reason": "already_processing"}

        async with get_db_session() as session:
            container = get_container()
            use_case = container.send_reply_use_case(session=session)
            result = await use_case.execute(
                comment_id=comment_id, reply_text=answer_text, use_generated_answer=not answer_text
            )

            if result["status"] == "retry" and self.request.retries < self.max_retries:
                raise self.retry(countdown=10)

            return result


@celery_app.task(bind=True, max_retries=3)
@async_task
async def hide_instagram_comment_task(self, comment_id: str):
    """Hide Instagram comment - orchestration only."""
    async with lock_manager.acquire(f"instagram_hide_lock:{comment_id}") as acquired:
        if not acquired:
            logger.info(f"Hide for {comment_id} already processing")
            return {"status": "skipped", "reason": "already_processing"}

        async with get_db_session() as session:
            container = get_container()
            use_case = container.hide_comment_use_case(session=session)
            result = await use_case.execute(comment_id, hide=True)

            if result["status"] == "retry" and self.request.retries < self.max_retries:
                raise self.retry(countdown=10)

            return result
