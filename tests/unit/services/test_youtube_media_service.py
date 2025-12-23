"""Unit tests for YouTubeMediaService."""

from __future__ import annotations

from datetime import timedelta

import pytest
from unittest.mock import AsyncMock, MagicMock

from core.config import settings
from core.repositories.media import MediaRepository
from core.services.youtube_media_service import YouTubeMediaService, QuotaExceeded
from core.utils.time import now_db_utc


def _video_payload(video_id: str):
    return {
        "items": [
            {
                "id": video_id,
                "snippet": {
                    "title": "Video Title",
                    "description": "Video description",
                    "channelTitle": "Channel Name",
                    "channelId": "chan-1",
                    "publishedAt": "2024-01-01T00:00:00Z",
                    "thumbnails": {
                        "high": {"url": "https://thumb/high.jpg"},
                        "medium": {"url": "https://thumb/med.jpg"},
                        "default": {"url": "https://thumb/def.jpg"},
                    },
                },
                "statistics": {
                    "commentCount": "10",
                    "likeCount": "5",
                },
            }
        ]
    }


@pytest.mark.asyncio
async def test_get_or_create_video_creates_new_media(db_session):
    yt_service = MagicMock()
    yt_service.get_video_details = AsyncMock(return_value=_video_payload("vid-1"))
    yt_service.list_captions = AsyncMock(
        return_value={
            "items": [
                {"id": "cap-1", "snippet": {"trackKind": "standard", "status": "serving"}},
            ]
        }
    )
    yt_service.download_caption = AsyncMock(return_value="WEBVTT\n\n1\n00:00:00.000 --> 00:00:01.000\nHi\n")
    service = YouTubeMediaService(youtube_service=yt_service)

    media = await service.get_or_create_video("vid-1", session=db_session)

    assert media is not None
    assert media.id == "vid-1"
    assert media.title == "Video Title"
    assert media.username == "Channel Name"
    assert media.platform == "youtube"
    assert media.subtitles is not None
    # Verify persisted in DB
    repo = MediaRepository(db_session)
    fetched = await repo.get_by_id("vid-1")
    assert fetched is not None


@pytest.mark.asyncio
async def test_get_or_create_video_returns_existing_on_fetch_error(db_session, media_factory):
    existing = await media_factory(media_id="vid-existing", media_type="VIDEO")
    yt_service = MagicMock()
    yt_service.get_video_details = AsyncMock(side_effect=RuntimeError("api down"))
    service = YouTubeMediaService(youtube_service=yt_service)

    media = await service.get_or_create_video(existing.id, session=db_session)

    assert media is existing  # falls back to cached record


@pytest.mark.asyncio
async def test_get_or_create_video_does_not_fetch_subtitles_for_existing(db_session, media_factory):
    existing = await media_factory(media_id="vid-existing", media_type="VIDEO")
    existing.updated_at = now_db_utc() - timedelta(seconds=settings.youtube.media_refresh_interval_seconds + 1)
    await db_session.commit()

    yt_service = MagicMock()
    yt_service.get_video_details = AsyncMock(return_value=_video_payload(existing.id))
    yt_service.list_captions = AsyncMock()
    yt_service.download_caption = AsyncMock()
    service = YouTubeMediaService(youtube_service=yt_service)

    media = await service.get_or_create_video(existing.id, session=db_session)

    assert media.id == existing.id
    yt_service.list_captions.assert_not_awaited()
    yt_service.download_caption.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_or_create_video_propagates_quota(db_session):
    yt_service = MagicMock()
    yt_service.get_video_details = AsyncMock(side_effect=QuotaExceeded("quota"))
    service = YouTubeMediaService(youtube_service=yt_service)

    with pytest.raises(QuotaExceeded):
        await service.get_or_create_video("vid-quota", session=db_session)
