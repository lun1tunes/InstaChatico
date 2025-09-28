import logging
from typing import Optional
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .instagram_service import InstagramGraphAPIService
from ..models import Media

logger = logging.getLogger(__name__)

class MediaService:
    """Service for managing Instagram media information"""
    
    def __init__(self, instagram_service: InstagramGraphAPIService = None):
        self.instagram_service = instagram_service or InstagramGraphAPIService()
    
    async def get_or_create_media(self, media_id: str, session: AsyncSession) -> Optional[Media]:
        """
        Get media from database or fetch from Instagram API if not exists
        
        Args:
            media_id: The Instagram media ID
            session: Database session
            
        Returns:
            Media object or None if failed
        """
        try:
            # First, check if media already exists in database
            existing_media = await session.execute(
                select(Media).where(Media.id == media_id)
            )
            media = existing_media.scalar_one_or_none()
            
            if media:
                logger.debug(f"Media {media_id} already exists in database")
                return media
            
            # Media doesn't exist, fetch from Instagram API
            logger.info(f"Media {media_id} not found in database, fetching from Instagram API")
            api_response = await self.instagram_service.get_media_info(media_id)
            
            if not api_response.get("success"):
                logger.error(f"Failed to fetch media info for {media_id}: {api_response.get('error')}")
                return None
            
            media_info = api_response["media_info"]
            
            # Create new Media object
            media = Media(
                id=media_id,
                permalink=media_info.get("permalink"),
                caption=media_info.get("caption"),
                media_url=media_info.get("media_url"),
                media_type=media_info.get("media_type"),
                comments_count=media_info.get("comments_count"),
                like_count=media_info.get("like_count"),
                shortcode=media_info.get("shortcode"),
                timestamp=self._parse_timestamp(media_info.get("timestamp")),
                is_comment_enabled=media_info.get("is_comment_enabled"),
                username=media_info.get("username"),
                owner=media_info.get("owner"),
                raw_data=media_info,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            # Add to session and commit
            session.add(media)
            await session.commit()
            await session.refresh(media)
            
            logger.info(f"Successfully created media record for {media_id}")
            return media
            
        except Exception as e:
            logger.error(f"Exception while getting/creating media {media_id}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            await session.rollback()
            return None
    
    def _parse_timestamp(self, timestamp_str: Optional[str]) -> Optional[datetime]:
        """
        Parse Instagram timestamp string to datetime object
        
        Args:
            timestamp_str: Instagram timestamp string (ISO format)
            
        Returns:
            datetime object or None
        """
        if not timestamp_str:
            return None
        
        try:
            # Instagram timestamps are typically in ISO format
            return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError) as e:
            logger.warning(f"Failed to parse timestamp '{timestamp_str}': {e}")
            return None
