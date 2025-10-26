"""Service for fetching media images with streaming support."""

from __future__ import annotations

from typing import AsyncIterator, Optional

import aiohttp


class MediaImageFetchResultImpl:
    """Concrete fetch result wrapping aiohttp response."""

    def __init__(self, session: aiohttp.ClientSession, response: aiohttp.ClientResponse):
        self._session = session
        self._response = response
        self._closed = False

    @property
    def status(self) -> int:
        return self._response.status

    @property
    def content_type(self) -> Optional[str]:
        return self._response.headers.get("Content-Type")

    @property
    def cache_control(self) -> Optional[str]:
        return self._response.headers.get("Cache-Control")

    def iter_bytes(self) -> AsyncIterator[bytes]:
        async def generator():
            try:
                async for chunk in self._response.content.iter_chunked(8192):
                    yield chunk
            finally:
                await self.close()

        return generator()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self._response.release()
        finally:
            self._response.close()
            await self._session.close()


class MediaProxyService:
    """Fetches media files via HTTP with controllable timeout."""

    def __init__(self, timeout_seconds: float = 20.0):
        self._timeout = timeout_seconds

    async def fetch_image(self, url: str) -> MediaImageFetchResultImpl:
        timeout = aiohttp.ClientTimeout(total=self._timeout)
        session = aiohttp.ClientSession(timeout=timeout)
        try:
            response = await session.get(url)
        except Exception:
            await session.close()
            raise
        return MediaImageFetchResultImpl(session=session, response=response)
