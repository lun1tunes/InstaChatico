"""Media processing tasks - refactored using Clean Architecture."""

import logging

from ..celery_app import celery_app
from ..use_cases.process_media import ProcessMediaUseCase, AnalyzeMediaUseCase
from ..utils.task_helpers import async_task, get_db_session
from ..container import get_container

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, queue="llm_queue")
@async_task
async def process_media_task(self, media_id: str):
    """Process media - orchestration only."""
    async with get_db_session() as session:
        container = get_container()
        use_case = container.process_media_use_case(session=session)
        result = await use_case.execute(media_id)

        # Handle retry logic - MediaCreateResult is a Pydantic model, not a dict
        if result.status == "retry" and self.request.retries < self.max_retries:
            raise self.retry(countdown=10)

        return result


@celery_app.task(bind=True, max_retries=3, queue="llm_queue")
@async_task
async def analyze_media_image_task(self, media_id: str):
    """Analyze media image - orchestration only."""
    async with get_db_session() as session:
        container = get_container()
        use_case = container.analyze_media_use_case(session=session)
        result = await use_case.execute(media_id)

        # Handle retry logic - MediaAnalysisResult is a Pydantic model, not a dict
        if result.status == "retry" and self.request.retries < self.max_retries:
            raise self.retry(countdown=10)

        return result
