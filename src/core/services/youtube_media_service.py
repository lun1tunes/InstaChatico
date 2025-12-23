"""YouTube video persistence service using MediaRepository."""

from __future__ import annotations

import logging
from typing import Optional, Dict, Any
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.interfaces.services import IYouTubeService
from core.models import Media
from core.repositories.media import MediaRepository
from core.utils.time import now_db_utc
from core.services.youtube_service import QuotaExceeded

logger = logging.getLogger(__name__)


def _parse_iso8601(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        logger.debug("Failed to parse datetime: %s", value)
        return None


class YouTubeMediaService:
    """Stores YouTube video metadata in the Media table for LLM context."""

    def __init__(self, youtube_service: IYouTubeService):
        self.youtube_service = youtube_service

    async def get_or_create_media(self, media_id: str, session: AsyncSession) -> Optional[Media]:
        """Compatibility wrapper for existing use cases (media == video)."""
        return await self.get_or_create_video(media_id, session)

    async def get_or_create_video(self, video_id: str, session: AsyncSession) -> Optional[Media]:
        repo = MediaRepository(session)
        existing = await repo.get_by_id(video_id)
        # Refresh only if stale to minimize YouTube quota usage.
        if existing and existing.updated_at:
            age_seconds = (now_db_utc() - existing.updated_at).total_seconds()
            if age_seconds < settings.youtube.media_refresh_interval_seconds:
                return existing

        try:
            details = await self.youtube_service.get_video_details(video_id)
        except QuotaExceeded:
            # Let caller handle quota exhaustion (propagate to polling logic)
            raise
        except Exception as exc:  # noqa: BLE001
            # If we already have a cached record, return it to preserve resilience
            if existing:
                logger.warning(
                    "Using cached video details due to fetch error | video_id=%s | error=%s",
                    video_id,
                    exc,
                )
                return existing
            logger.error("Failed to fetch video details | video_id=%s | error=%s", video_id, exc)
            return None

        items = details.get("items") or []
        if not items:
            logger.warning("Video not found on YouTube | video_id=%s", video_id)
            return None

        video = items[0]
        snippet: Dict[str, Any] = video.get("snippet", {})
        stats: Dict[str, Any] = video.get("statistics", {})
        thumbnails = snippet.get("thumbnails", {}) or {}
        # Pick high-res thumbnail if available
        thumb_url = (
            thumbnails.get("high", {}).get("url")
            or thumbnails.get("medium", {}).get("url")
            or thumbnails.get("default", {}).get("url")
        )

        if existing:
            # Refresh missing/critical fields for legacy records
            existing.platform = "youtube"
            existing.title = existing.title or snippet.get("title")
            existing.caption = existing.caption or snippet.get("description")
            existing.username = existing.username or snippet.get("channelTitle")
            existing.owner = existing.owner or snippet.get("channelId")
            existing.comments_count = _safe_int(stats.get("commentCount"))
            existing.like_count = _safe_int(stats.get("likeCount"))
            existing.media_url = existing.media_url or thumb_url
            existing.permalink = existing.permalink or f"https://www.youtube.com/watch?v={video_id}"
            existing.posted_at = existing.posted_at or _parse_iso8601(snippet.get("publishedAt"))
            existing.raw_data = video
            existing.updated_at = now_db_utc()
            await session.commit()
            await session.refresh(existing)
            return existing

        subtitles = await self._fetch_subtitles(video_id)

        media = Media(
            id=video_id,
            platform="youtube",
            permalink=f"https://www.youtube.com/watch?v={video_id}",
            title=snippet.get("title"),
            caption=snippet.get("description"),
            media_url=thumb_url,
            media_type="VIDEO",
            subtitles=subtitles,
            comments_count=_safe_int(stats.get("commentCount")),
            like_count=_safe_int(stats.get("likeCount")),
            shortcode=None,
            posted_at=_parse_iso8601(snippet.get("publishedAt")),
            is_comment_enabled=True,
            is_processing_enabled=True,
            username=snippet.get("channelTitle"),
            owner=snippet.get("channelId"),
            raw_data=video,
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )

        media = await repo.create(media)
        await session.commit()
        await session.refresh(media)
        return media

    async def _fetch_subtitles(self, video_id: str) -> Optional[str]:
        """Best-effort subtitle fetch for new YouTube media."""
        try:
            caption_list = await self.youtube_service.list_captions(video_id=video_id)
        except QuotaExceeded:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.info("Captions list failed | video_id=%s | error=%s", video_id, exc)
            return None

        items = caption_list.get("items") or []
        caption_id = _select_caption_id(items)
        if not caption_id:
            return None

        try:
            payload = await self.youtube_service.download_caption(caption_id=caption_id, tfmt="vtt")
        except QuotaExceeded:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.info("Caption download failed | video_id=%s | caption_id=%s | error=%s", video_id, caption_id, exc)
            return None

        if payload is None:
            return None
        if isinstance(payload, bytes):
            return payload.decode("utf-8", errors="replace")
        if isinstance(payload, str):
            return payload
        return str(payload)


def _safe_int(value) -> Optional[int]:
    try:
        return int(value)
    except Exception:
        return None


def _select_caption_id(items: list[dict]) -> Optional[str]:
    if not items:
        return None

    def score(item: dict) -> tuple[int, int]:
        snippet = item.get("snippet", {}) or {}
        track_kind = (snippet.get("trackKind") or "").lower()
        status = (snippet.get("status") or "").lower()
        is_asr = 1 if track_kind == "asr" else 0
        is_failed = 1 if status == "failed" else 0
        return (is_failed, is_asr)

    sorted_items = sorted(items, key=score)
    for item in sorted_items:
        caption_id = item.get("id")
        if caption_id:
            return caption_id
    return None
