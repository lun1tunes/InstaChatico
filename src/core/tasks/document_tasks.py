"""Document processing tasks - refactored using Clean Architecture."""

import logging

from core.celery_app import celery_app
from core.utils.task_helpers import async_task, get_db_session
from core.container import get_container

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, queue="llm_queue")
@async_task
async def process_document_task(self, document_id: str):
    """Process document - orchestration only."""
    async with get_db_session() as session:
        container = get_container()
        use_case = container.process_document_use_case(session=session)
        result = await use_case.execute(document_id)

        if result["status"] == "retry" and self.request.retries < self.max_retries:
            raise self.retry(countdown=10)

        return result
