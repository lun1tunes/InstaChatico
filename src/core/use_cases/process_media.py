"""Process media use case - handles media processing business logic."""

from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models import Media
from ..services.media_service import MediaService
from ..services.media_analysis_service import MediaAnalysisService
from ..utils.decorators import handle_task_errors


class ProcessMediaUseCase:
    """Use case for processing Instagram media (fetch + analyze)."""

    def __init__(self, session: AsyncSession, media_service=None, analysis_service=None):
        self.session = session
        self.media_service = media_service or MediaService()
        self.analysis_service = analysis_service or MediaAnalysisService()

    @handle_task_errors()
    async def execute(self, media_id: str) -> Dict[str, Any]:
        """Execute media processing use case."""
        # 1. Check if media exists
        result = await self.session.execute(
            select(Media).where(Media.id == media_id)
        )
        existing_media = result.scalar_one_or_none()

        if existing_media:
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

        # 2. Fetch from Instagram API
        media = await self.media_service.get_or_create_media(media_id, self.session)

        if not media:
            return {
                "status": "error",
                "media_id": media_id,
                "reason": "api_fetch_failed",
            }

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


class AnalyzeMediaUseCase:
    """Use case for analyzing media images with AI."""

    def __init__(self, session: AsyncSession, analysis_service=None):
        self.session = session
        self.analysis_service = analysis_service or MediaAnalysisService()

    @handle_task_errors()
    async def execute(self, media_id: str) -> Dict[str, Any]:
        """Execute media analysis use case."""
        # 1. Get media
        result = await self.session.execute(
            select(Media).where(Media.id == media_id)
        )
        media = result.scalar_one_or_none()

        if not media:
            return {"status": "error", "reason": f"Media {media_id} not found"}

        # 2. Check if already analyzed
        if media.media_context:
            return {
                "status": "skipped",
                "reason": "already_analyzed",
                "media_id": media_id,
            }

        # 3. Check if media has image
        if media.media_type not in ["IMAGE", "CAROUSEL_ALBUM"] or not media.media_url:
            return {
                "status": "skipped",
                "reason": "no_image_to_analyze",
                "media_type": media.media_type,
            }

        # 4. Analyze image
        analysis_result = await self.analysis_service.analyze_media_image(
            media_url=media.media_url,
            media_type=media.media_type,
            caption=media.caption,
        )

        if analysis_result.get("success"):
            media.media_context = analysis_result.get("description")
            await self.session.commit()

            return {
                "status": "success",
                "media_id": media_id,
                "media_context": media.media_context,
            }
        else:
            return {
                "status": "error",
                "reason": analysis_result.get("error", "Analysis failed"),
            }
