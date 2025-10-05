"""Telegram notification tasks - refactored using Clean Architecture."""

import logging

from ..celery_app import celery_app
from ..use_cases.send_telegram_notification import SendTelegramNotificationUseCase
from ..utils.task_helpers import async_task, get_db_session

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
@async_task
async def send_telegram_notification_task(self, comment_id: str):
    """Send Telegram notification - orchestration only."""
    async with get_db_session() as session:
        use_case = SendTelegramNotificationUseCase(session)
        result = await use_case.execute(comment_id)

        if result["status"] == "retry" and self.request.retries < self.max_retries:
            raise self.retry(countdown=10)

        return result
