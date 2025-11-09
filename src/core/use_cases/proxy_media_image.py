"""Use case for proxying media images through backend."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional, Sequence
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from core.interfaces.repositories import IMediaRepository
from core.interfaces.services import IMediaProxyService, IMediaService

logger = logging.getLogger(__name__)


@dataclass
class MediaImageUrlResult:
    media_url: str


class MediaImageProxyError(Exception):
    def __init__(self, status_code: int, code: int, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


class ProxyMediaImageUseCase:
    """Retrieve media image content via proxy with host validation."""

    def __init__(
        self,
        session: AsyncSession,
        media_repository_factory: Callable[..., IMediaRepository],
        proxy_service: IMediaProxyService,
        allowed_host_suffixes: Sequence[str],
        media_service: Optional[IMediaService] = None,
    ):
        self.session = session
        self.media_repo: IMediaRepository = media_repository_factory(session=session)
        self.proxy_service = proxy_service
        self.media_service = media_service
        self.allowed_hosts = tuple(host.lower() for host in allowed_host_suffixes)

    async def execute(self, media_id: str, child_index: Optional[int] = None) -> MediaImageUrlResult:
        logger.debug(
            "Proxy media image use case started | media_id=%s | child_index=%s",
            media_id,
            child_index,
        )

        media = await self.media_repo.get_by_id(media_id)
        if not media:
            logger.warning("Media not found for proxy | media_id=%s", media_id)
            raise MediaImageProxyError(404, 4040, "Media not found")

        image_url = self._select_media_image_url(media, child_index)
        if not image_url:
            logger.warning(
                "Media image not available | media_id=%s | child_index=%s",
                media_id,
                child_index,
            )
            raise MediaImageProxyError(404, 4043, "Media image not available")

        parsed = urlparse(image_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            logger.error(
                "Invalid media image URL | media_id=%s | url=%s",
                media_id,
                image_url,
            )
            raise MediaImageProxyError(400, 4003, "Invalid media image URL")

        if not self._is_allowed_host(parsed.netloc):
            logger.error(
                "Disallowed media image host | media_id=%s | host=%s",
                media_id,
                parsed.netloc,
            )
            raise MediaImageProxyError(400, 4004, "Image host not allowed")

        attempted_refresh = False
        while True:
            try:
                fetch_result = await self.proxy_service.fetch_image(image_url)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Media proxy service error | media_id=%s | url=%s | error=%s",
                    media_id,
                    image_url,
                    exc,
                )
                raise MediaImageProxyError(502, 5005, f"Error fetching media image: {exc}") from exc

            if fetch_result.status == 200:
                await fetch_result.close()
                break

            await fetch_result.close()

            if (
                not attempted_refresh
                and self.media_service is not None
                and fetch_result.status in {401, 403, 404}
            ):
                logger.info(
                    "Attempting to refresh media URLs after fetch failure | media_id=%s | status=%s",
                    media_id,
                    fetch_result.status,
                )
                refreshed_media = await self.media_service.refresh_media_urls(media_id, self.session)
                attempted_refresh = True

                if not refreshed_media:
                    logger.error(
                        "Media URL refresh failed | media_id=%s | status=%s",
                        media_id,
                        fetch_result.status,
                    )
                    raise MediaImageProxyError(502, 5003, "Failed to refresh media image")

                media = refreshed_media
                image_url = self._select_media_image_url(media, child_index)
                if not image_url:
                    logger.warning(
                        "Media image unavailable after refresh | media_id=%s | child_index=%s",
                        media_id,
                        child_index,
                    )
                    raise MediaImageProxyError(404, 4043, "Media image not available after refresh")

                parsed = urlparse(image_url)
                if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                    logger.error(
                        "Invalid refreshed media image URL | media_id=%s | url=%s",
                        media_id,
                        image_url,
                    )
                    raise MediaImageProxyError(400, 4003, "Invalid media image URL after refresh")

                if not self._is_allowed_host(parsed.netloc):
                    logger.error(
                        "Disallowed host after refresh | media_id=%s | host=%s",
                        media_id,
                        parsed.netloc,
                    )
                    raise MediaImageProxyError(400, 4004, "Image host not allowed after refresh")
                continue

            logger.error(
                "Unexpected status from media proxy | media_id=%s | url=%s | status=%s",
                media_id,
                image_url,
                fetch_result.status,
            )
            raise MediaImageProxyError(502, 5003, f"Failed to fetch media image (status {fetch_result.status})")

        logger.debug(
            "Media proxy response prepared | media_id=%s | child_index=%s | media_url=%s",
            media_id,
            child_index,
            image_url,
        )
        return MediaImageUrlResult(media_url=image_url)

    def _select_media_image_url(self, media, child_index: Optional[int]) -> Optional[str]:
        if child_index is None:
            return getattr(media, "media_url", None)

        children = getattr(media, "children_media_urls", None) or []
        if not isinstance(children, list) or not children:
            return getattr(media, "media_url", None)

        if child_index < 0 or child_index >= len(children):
            return None
        return children[child_index]

    def _is_allowed_host(self, netloc: str) -> bool:
        normalized = netloc.lower()
        return any(normalized.endswith(suffix) for suffix in self.allowed_hosts)
