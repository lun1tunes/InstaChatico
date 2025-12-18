"""YouTube Data API service: comments, replies, video metadata."""

from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import Any, Optional, Callable
from typing import cast

# Optional Google client imports – guarded to avoid hard dependency at import time.
try:  # pragma: no cover - import guard
    from google.oauth2.credentials import Credentials  # type: ignore
    from google.auth.transport.requests import Request  # type: ignore
    from googleapiclient.discovery import build, Resource  # type: ignore
    from googleapiclient.errors import HttpError  # type: ignore
    try:
        from google.auth.exceptions import RefreshError  # type: ignore
    except Exception:  # pragma: no cover - fallback
        class RefreshError(Exception):  # type: ignore
            ...
    _google_import_error: Exception | None = None
except Exception as _exc:  # pragma: no cover - fallback for missing deps
    Credentials = None  # type: ignore
    Request = None  # type: ignore
    Resource = Any  # type: ignore
    build = None  # type: ignore
    HttpError = Exception  # type: ignore
    RefreshError = Exception  # type: ignore
    _google_import_error = _exc
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.config import settings


class MissingYouTubeAuth(Exception):
    """Raised when no valid YouTube OAuth tokens are available."""


class QuotaExceeded(Exception):
    """Raised when YouTube Data API quota is exhausted."""


logger = logging.getLogger(__name__)

YOUTUBE_SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"


def _ensure_google_imports() -> None:
    """Raise a helpful error if Google client libraries are missing."""
    if _google_import_error:
        raise ImportError(
            "Google API client libraries are not installed. "
            "Install with: pip install google-api-python-client google-auth google-auth-oauthlib cryptography"
        ) from _google_import_error


class YouTubeService:
    """Lightweight async wrapper around YouTube Data API v3."""

    def __init__(
        self,
        *,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        refresh_token: Optional[str] = None,
        api_key: Optional[str] = None,
        channel_id: Optional[str] = None,
        token_service_factory: Optional[Callable[..., Any]] = None,
        session_factory: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.client_id = client_id or settings.youtube.client_id
        self.client_secret = client_secret or settings.youtube.client_secret
        self.refresh_token = refresh_token or settings.youtube.refresh_token
        self.api_key = api_key or settings.youtube.api_key
        self.channel_id = channel_id or settings.youtube.channel_id
        self.token_service_factory = token_service_factory
        self.session_factory = session_factory
        self._credentials: Credentials | None = None
        self._youtube: Resource | None = None
        self._account_id = self.channel_id or None
        self._uploads_playlist_cache: dict[str, str] = {}

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    async def _build_credentials(self) -> Credentials:
        """
        Build credentials strictly from stored OAuth tokens.

        Требование продукта: любые операции YouTube (в том числе polling) допускаются
        только при наличии токенов в нашей базе (OAuthTokenService). Поэтому здесь
        нет запасного варианта с переменными окружения.
        """
        _ensure_google_imports()
        assert Credentials is not None  # for type checkers

        tokens = await self._load_tokens()
        if tokens:
            if not self._account_id:
                self._account_id = tokens.get("account_id")
            return Credentials(
                tokens.get("access_token"),
                refresh_token=tokens.get("refresh_token"),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=self.client_id,
                client_secret=self.client_secret,
                scopes=[YOUTUBE_SCOPE],
                expiry=tokens.get("access_token_expires_at") or tokens.get("expires_at"),
            )

        raise MissingYouTubeAuth("No YouTube OAuth tokens available. Complete Google OAuth first.")

    async def _get_youtube(self) -> Resource:
        _ensure_google_imports()
        assert Credentials is not None and Request is not None and build is not None  # for type checkers

        if self._credentials is None:
            self._credentials = await self._build_credentials()

        # Refresh if needed
        if not self._credentials.valid:
            if not self._credentials.refresh_token:
                raise MissingYouTubeAuth("Missing refresh token for YouTube. Complete Google OAuth first.")
            try:
                self._credentials.refresh(Request())
                await self._persist_refreshed_tokens()
            except RefreshError as exc:  # pragma: no cover - handled at runtime
                msg = str(exc)
                if "invalid_grant" in msg or "invalid_client" in msg:
                    logger.warning("YouTube refresh token invalid or revoked; re-auth required. %s", msg)
                    raise MissingYouTubeAuth("YouTube refresh token invalid or revoked; reconnect YouTube.") from exc
                logger.error("Failed to refresh YouTube credentials: %s", exc, exc_info=True)
                raise
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to refresh YouTube credentials: %s", exc, exc_info=True)
                raise

        if self._youtube is None:
            self._youtube = cast(
                Resource,
                build("youtube", "v3", credentials=self._credentials, cache_discovery=False),
            )

        return self._youtube

    async def _run(self, func, *args, **kwargs) -> Any:
        """Run blocking Google client calls in a thread."""
        return await asyncio.to_thread(func, *args, **kwargs)

    async def _load_tokens(self) -> Optional[dict]:
        """Load tokens from secure storage if configured."""
        if not self.token_service_factory or not self.session_factory:
            return None
        try:
            session_factory = self.session_factory
            # Resolve to an actual session instance, handling factories or sessionmaker
            factory_result = session_factory() if callable(session_factory) else session_factory

            if isinstance(factory_result, async_sessionmaker):
                session_cm = factory_result()
            else:
                session_cm = factory_result

            async with session_cm as session:  # type: ignore
                token_service = self.token_service_factory(session=session)
                return await token_service.get_tokens("google", self._account_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load stored OAuth tokens | error=%s", exc)
            return None

    async def _persist_refreshed_tokens(self) -> None:
        """Persist refreshed access token if storage is configured."""
        if not self.token_service_factory or not self.session_factory or not self._credentials:
            return
        # Only persist if we have a refresh token (either stored or env)
        refresh_token = self._credentials.refresh_token or self.refresh_token
        if not refresh_token:
            return
        expires_at = self._credentials.expiry
        try:
            session_factory = self.session_factory
            factory_result = session_factory() if callable(session_factory) else session_factory

            if isinstance(factory_result, async_sessionmaker):
                session_cm = factory_result()
            else:
                session_cm = factory_result

            async with session_cm as session:  # type: ignore
                token_service = self.token_service_factory(session=session)
                await token_service.update_access_token(
                    provider="google",
                    account_id=self._account_id or "default",
                    access_token=self._credentials.token,
                    access_token_expires_at=expires_at,
                    refresh_token=refresh_token,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to persist refreshed OAuth tokens | error=%s", exc)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    async def list_channel_videos(
        self,
        channel_id: Optional[str] = None,
        page_token: Optional[str] = None,
        max_results: int = 50,
    ) -> dict:
        """List videos for a channel (latest first) using uploads playlist (cheaper than search)."""
        youtube = await self._get_youtube()

        playlist_id = await self._get_uploads_playlist_id(channel_id=channel_id)
        if not playlist_id:
            raise MissingYouTubeAuth("Unable to resolve uploads playlist id; ensure OAuth is completed.")

        def _call():
            return (
                youtube.playlistItems()
                .list(
                    part="contentDetails",
                    playlistId=playlist_id,
                    maxResults=max_results,
                    pageToken=page_token,
                )
                .execute()
            )

        return await self._execute(_call)

    async def get_account_id(self) -> Optional[str]:
        """Return the active channel/account id."""
        if self._account_id:
            return self._account_id
        tokens = await self._load_tokens()
        if tokens and tokens.get("account_id"):
            self._account_id = tokens["account_id"]
            return self._account_id

        # Try to resolve via API using current credentials
        try:
            youtube = await self._get_youtube()

            def _call():
                return youtube.channels().list(part="id", mine=True).execute()

            resp = await self._execute(_call)
            items = resp.get("items") or []
            if items:
                self._account_id = items[0].get("id")
                return self._account_id
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to resolve YouTube channel id via API | error=%s", exc)

        self._account_id = self.channel_id or None
        return self._account_id

    async def _get_uploads_playlist_id(self, channel_id: Optional[str]) -> Optional[str]:
        """Resolve the uploads playlist ID for a channel, caching the result."""
        target_channel = channel_id or self.channel_id

        # Try cache first
        if target_channel and target_channel in self._uploads_playlist_cache:
            return self._uploads_playlist_cache[target_channel]

        youtube = await self._get_youtube()

        def _call():
            # If no explicit channel, use mine=true
            params = {"part": "contentDetails"}
            if target_channel:
                params["id"] = target_channel
            else:
                params["mine"] = True
            return youtube.channels().list(**params).execute()

        resp = await self._execute(_call)
        items = resp.get("items") or []
        if not items:
            return None
        uploads_id = items[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
        if uploads_id and target_channel:
            self._uploads_playlist_cache[target_channel] = uploads_id
        return uploads_id

    async def list_comment_threads(
        self,
        video_id: str,
        page_token: Optional[str] = None,
        max_results: int = 50,
        order: str = "time",
    ) -> dict:
        """Fetch top-level comment threads (includes replies summary)."""
        youtube = await self._get_youtube()

        def _call():
            return (
                youtube.commentThreads()
                .list(
                    part="snippet,replies",
                    videoId=video_id,
                    textFormat="plainText",
                    order=order,
                    maxResults=max_results,
                    pageToken=page_token,
                )
                .execute()
            )

        return await self._execute(_call)

    async def list_comment_replies(
        self,
        parent_id: str,
        page_token: Optional[str] = None,
        max_results: int = 100,
    ) -> dict:
        """Fetch replies for a given top-level comment (comments.list parentId)."""
        youtube = await self._get_youtube()

        def _call():
            return (
                youtube.comments()
                .list(
                    part="snippet",
                    parentId=parent_id,
                    textFormat="plainText",
                    maxResults=max_results,
                    pageToken=page_token,
                )
                .execute()
            )

        return await self._execute(_call)

    async def reply_to_comment(self, parent_id: str, text: str) -> dict:
        """Post a reply to an existing comment."""
        youtube = await self._get_youtube()

        body = {"snippet": {"parentId": parent_id, "textOriginal": text}}

        def _call():
            return youtube.comments().insert(part="snippet", body=body).execute()

        return await self._execute(_call)

    async def delete_comment(self, comment_id: str) -> None:
        """Delete a comment (moderation action)."""
        youtube = await self._get_youtube()

        def _call():
            return youtube.comments().delete(id=comment_id).execute()

        await self._execute(_call)

    async def get_video_details(self, video_id: str) -> dict:
        """Fetch video metadata + stats for media context."""
        youtube = await self._get_youtube()

        def _call():
            return (
                youtube.videos()
                .list(
                    part="snippet,statistics,contentDetails",
                    id=video_id,
                )
                .execute()
            )

        return await self._execute(_call)

    async def _execute(self, call):
        """Execute Google API call with uniform error handling and simple backoff."""
        attempt = 0
        while True:
            attempt += 1
            try:
                return await self._run(call)
            except HttpError as http_err:
                status = getattr(http_err, "status_code", None) or getattr(http_err, "resp", None)
                logger.error("YouTube API error: %s | status=%s", http_err, status)
                if hasattr(http_err, "error_details") and http_err.error_details:
                    logger.error("YouTube error details: %s", http_err.error_details)
                    if any(d.get("reason") in {"invalidGrant", "invalidCredentials"} for d in http_err.error_details if isinstance(d, dict)):
                        raise MissingYouTubeAuth("YouTube credentials invalid; reconnect required.") from http_err
                    # Detect quota exhaustion explicitly
                    if any(d.get("reason") == "quotaExceeded" for d in http_err.error_details if isinstance(d, dict)):
                        raise QuotaExceeded("YouTube quota exceeded") from http_err
                # Basic quota/backoff handling
                if getattr(http_err, "res", None) and getattr(http_err.res, "status", None) == 403:
                    # Small exponential backoff
                    delay = min(30, 2 ** attempt)
                    logger.warning("Quota or permission error, backing off for %ss (attempt %s)", delay, attempt)
                    await asyncio.sleep(delay)
                    continue
                raise
            except Exception as exc:  # noqa: BLE001
                logger.error("YouTube service unexpected error: %s", exc, exc_info=True)
                raise
