import asyncio
import logging
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from ..celery_app import celery_app
from ..models import Media
from ..services.media_service import MediaService
from ..services.media_analysis_service import MediaAnalysisService
from ..config import settings
from ..utils.task_helpers import async_task, get_db_session, retry_with_backoff

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, queue="llm_queue")
def process_media_task(self, media_id: str):
    """Синхронная обертка для асинхронной задачи обработки медиа"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(process_media_async(media_id, self))
    finally:
        loop.close()


async def process_media_async(media_id: str, task_instance=None):
    """Асинхронная задача обработки медиа - получение информации из Instagram API и сохранение в БД"""
    # Create a fresh engine and session for this task
    engine = create_async_engine(settings.db.url, echo=settings.db.echo)
    session_factory = async_sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    async with session_factory() as session:
        try:
            logger.info(f"Processing media {media_id}")

            # Check if media already exists
            result = await session.execute(select(Media).where(Media.id == media_id))
            existing_media = result.scalar_one_or_none()

            if existing_media:
                logger.debug(f"Media {media_id} already exists in database")
                return {
                    "status": "success",
                    "media_id": media_id,
                    "action": "already_exists",
                    "media": {
                        "id": existing_media.id,
                        "permalink": existing_media.permalink,
                        "username": existing_media.username,
                        "created_at": existing_media.created_at.isoformat() if existing_media.created_at else None,
                    },
                }

            # Media doesn't exist, fetch from Instagram API
            logger.debug(f"Media {media_id} not found in database, fetching from Instagram API")
            media_service = MediaService()
            media = await media_service.get_or_create_media(media_id, session)

            if not media:
                logger.error(f"Failed to fetch/create media {media_id}")
                return {"status": "error", "media_id": media_id, "reason": "api_fetch_failed"}

            logger.info(f"Successfully processed media {media_id}")
            return {
                "status": "success",
                "media_id": media_id,
                "action": "created",
                "media": {
                    "id": media.id,
                    "permalink": media.permalink,
                    "username": media.username,
                    "media_type": media.media_type,
                    "comments_count": media.comments_count,
                    "like_count": media.like_count,
                    "created_at": media.created_at.isoformat() if media.created_at else None,
                },
            }

        except Exception as exc:
            logger.exception(f"Error processing media {media_id}")
            await session.rollback()

            # Retry logic
            if task_instance and task_instance.request.retries < task_instance.max_retries:
                retry_countdown = 2**task_instance.request.retries * 60
                logger.warning(f"Retrying media processing for {media_id} in {retry_countdown} seconds")
                raise task_instance.retry(countdown=retry_countdown, exc=exc)

            return {"status": "error", "media_id": media_id, "reason": str(exc)}
        finally:
            await engine.dispose()


@celery_app.task(queue="llm_queue")
def process_media_batch_task(media_ids: list[str]):
    """Обработка нескольких медиа за раз"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(process_media_batch_async(media_ids))
    finally:
        loop.close()


async def process_media_batch_async(media_ids: list[str]):
    """Асинхронная обработка нескольких медиа"""
    results = []

    for media_id in media_ids:
        try:
            result = await process_media_async(media_id)
            results.append(result)
        except Exception as e:
            logger.exception(f"Error processing media {media_id} in batch")
            results.append({"status": "error", "media_id": media_id, "reason": str(e)})

    logger.info(f"Processed {len(media_ids)} media items")
    return {"status": "completed", "total": len(media_ids), "results": results}


@celery_app.task(bind=True, max_retries=3, queue="llm_queue")
@async_task
async def analyze_media_image_task(self, media_id: str):
    """Analyze media image and store context using AI."""
    return await analyze_media_image_async(media_id, self)


async def analyze_media_image_async(media_id: str, task_instance=None):
    """Async task to analyze media image and update media_context field."""
    async with get_db_session() as session:
        try:
            logger.info(f"Starting media image analysis for {media_id}")

            # Get media from database
            result = await session.execute(select(Media).where(Media.id == media_id))
            media = result.scalar_one_or_none()

            if not media:
                logger.warning(f"Media {media_id} not found for analysis")
                return {"status": "error", "reason": "media_not_found"}

            # Check if media has URL and is an image
            if not media.media_url:
                logger.info(f"Media {media_id} has no media_url, skipping analysis")
                return {"status": "skipped", "reason": "no_media_url"}

            if media.media_type not in ["IMAGE", "CAROUSEL_ALBUM"]:
                logger.info(
                    f"Media {media_id} is type {media.media_type}, skipping analysis (only IMAGE and CAROUSEL supported)"
                )
                return {"status": "skipped", "reason": f"unsupported_type_{media.media_type}"}

            # Check if already analyzed
            if media.media_context:
                logger.info(f"Media {media_id} already has context, skipping re-analysis")
                return {"status": "skipped", "reason": "already_analyzed"}

            # Perform AI analysis
            logger.debug(f"Analyzing image at URL: {media.media_url}")
            analysis_service = MediaAnalysisService()
            media_context = await analysis_service.analyze_media_image(media_url=media.media_url, caption=media.caption)

            if not media_context:
                logger.error(f"Failed to analyze media {media_id} - no context returned")
                return retry_with_backoff(task_instance, Exception("Analysis returned empty result"))

            # Update media with context
            media.media_context = media_context
            await session.commit()

            logger.info(
                f"Successfully analyzed and updated media {media_id}. Context length: {len(media_context)} chars"
            )

            return {
                "status": "success",
                "media_id": media_id,
                "context_length": len(media_context),
            }

        except Exception as exc:
            logger.exception(f"Error analyzing media image {media_id}")
            await session.rollback()
            return retry_with_backoff(task_instance, exc)
