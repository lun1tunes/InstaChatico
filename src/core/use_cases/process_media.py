"""Process media use case - handles media processing business logic."""

import logging
from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories.media import MediaRepository
from ..services.media_service import MediaService
from ..services.media_analysis_service import MediaAnalysisService
from ..utils.decorators import handle_task_errors
from ..schemas.media import MediaCreateResult, MediaAnalysisResult

logger = logging.getLogger(__name__)


class ProcessMediaUseCase:
    """Use case for processing Instagram media (fetch + analyze)."""

    def __init__(self, session: AsyncSession, media_service=None, analysis_service=None):
        self.session = session
        self.media_repo = MediaRepository(session)
        self.media_service = media_service or MediaService()
        self.analysis_service = analysis_service or MediaAnalysisService()

    @handle_task_errors()
    async def execute(self, media_id: str) -> MediaCreateResult:
        """Execute media processing use case."""
        # 1. Check if media exists using repository
        existing_media = await self.media_repo.get_by_id(media_id)

        if existing_media:
            return MediaCreateResult(
                status="success",
                media_id=media_id,
                action="already_exists",
                media={
                    "id": existing_media.id,
                    "permalink": existing_media.permalink,
                    "username": existing_media.username,
                    "created_at": existing_media.created_at.isoformat() if existing_media.created_at else None,
                },
            )

        # 2. Fetch from Instagram API
        media = await self.media_service.get_or_create_media(media_id, self.session)

        if not media:
            return MediaCreateResult(
                status="error",
                media_id=media_id,
                reason="api_fetch_failed",
            )

        return MediaCreateResult(
            status="success",
            media_id=media_id,
            action="created",
            media={
                "id": media.id,
                "permalink": media.permalink,
                "username": media.username,
                "media_type": media.media_type,
                "comments_count": media.comments_count,
                "like_count": media.like_count,
                "created_at": media.created_at.isoformat() if media.created_at else None,
            },
        )


class AnalyzeMediaUseCase:
    """Use case for analyzing media images with AI."""

    def __init__(self, session: AsyncSession, analysis_service=None):
        self.session = session
        self.media_repo = MediaRepository(session)
        self.analysis_service = analysis_service or MediaAnalysisService()

    @handle_task_errors()
    async def execute(self, media_id: str) -> MediaAnalysisResult:
        """Execute media analysis use case."""
        # 1. Get media using repository
        media = await self.media_repo.get_by_id(media_id)

        if not media:
            return MediaAnalysisResult(
                status="error",
                media_id=media_id,
                reason=f"Media {media_id} not found"
            )

        # 2. Check if already analyzed
        if media.media_context:
            return MediaAnalysisResult(
                status="skipped",
                media_id=media_id,
                reason="already_analyzed",
            )

        # 3. Check if media has image(s)
        if media.media_type not in ["IMAGE", "CAROUSEL_ALBUM"] or not media.media_url:
            return MediaAnalysisResult(
                status="skipped",
                media_id=media_id,
                reason="no_image_to_analyze",
            )

        # 4. Analyze image(s)
        # For CAROUSEL_ALBUM with multiple children, analyze all images
        if media.media_type == "CAROUSEL_ALBUM" and media.children_media_urls:
            logger.info(f"Analyzing carousel with {len(media.children_media_urls)} images for media {media_id}")
            analysis_result = await self.analysis_service.analyze_carousel_images(
                media_urls=media.children_media_urls,
                caption=media.caption,
            )
        else:
            # Single image or carousel without children URLs (fallback)
            logger.info(f"Analyzing single image for media {media_id}")
            analysis_result = await self.analysis_service.analyze_media_image(
                media_url=media.media_url,
                caption=media.caption,
            )

        if analysis_result:
            media.media_context = analysis_result
            await self.session.commit()

            return MediaAnalysisResult(
                status="success",
                media_id=media_id,
                media_context=media.media_context,
                images_analyzed=len(media.children_media_urls) if media.children_media_urls else 1,
            )
        else:
            return MediaAnalysisResult(
                status="error",
                media_id=media_id,
                reason="Analysis failed - no result returned",
            )
