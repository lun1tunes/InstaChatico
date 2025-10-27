import inspect
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, Protocol, Tuple

import aiohttp
from aiolimiter import AsyncLimiter

from ..config import settings

logger = logging.getLogger(__name__)


class RateLimiterProtocol(Protocol):
    max_rate: int
    time_period: int

    async def acquire(self) -> Tuple[bool, float]:
        ...


class _AsyncLimiterAdapter:
    """Adapter to match AsyncLimiter interface to RateLimiterProtocol."""

    def __init__(self, limiter: AsyncLimiter):
        self._limiter = limiter
        self.max_rate = limiter.max_rate
        self.time_period = limiter.time_period

    async def acquire(self) -> Tuple[bool, float]:
        async with self._limiter:
            return True, 0.0

    async def close(self) -> None:
        # AsyncLimiter does not require explicit close; provided for symmetry.
        return None


class InstagramGraphAPIService:
    """Service for interacting with Instagram Graph API."""

    def __init__(
        self,
        access_token: str = None,
        session: Optional[aiohttp.ClientSession] = None,
        rate_limiter: Optional[RateLimiterProtocol] = None,
    ):
        self.access_token = access_token or settings.instagram.access_token
        self.base_url = f"https://graph.instagram.com/{settings.instagram.api_version}"

        if not self.access_token:
            raise ValueError("Instagram access token is required")

        self._session = session
        self._should_close_session = session is None
        if rate_limiter is not None:
            self._reply_rate_limiter: RateLimiterProtocol = rate_limiter
            self._owns_rate_limiter = False
        else:
            self._reply_rate_limiter = _AsyncLimiterAdapter(
                AsyncLimiter(
                    max_rate=settings.instagram.replies_rate_limit_per_hour,
                    time_period=settings.instagram.replies_rate_period_seconds,
                )
            )
            self._owns_rate_limiter = True

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                connector=aiohttp.TCPConnector(limit=100, limit_per_host=30)
            )
            self._should_close_session = True
            logger.debug("Created new aiohttp.ClientSession")
        return self._session

    async def close(self):
        """Close the aiohttp session."""
        if self._session and not self._session.closed and self._should_close_session:
            await self._session.close()
            logger.info("InstagramGraphAPIService session closed")
        if self._owns_rate_limiter and hasattr(self._reply_rate_limiter, "close"):
            closer = getattr(self._reply_rate_limiter, "close")
            if inspect.iscoroutinefunction(closer):
                await closer()
            else:
                closer()

    async def __aenter__(self):
        """Context manager support."""
        await self._get_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup."""
        await self.close()

    async def send_reply_to_comment(self, comment_id: str, message: str) -> Dict[str, Any]:
        """Send reply to Instagram comment via Graph API."""
        url = f"{self.base_url}/{comment_id}/replies"
        params = {"access_token": self.access_token, "message": message}

        logger.info(
            f"Sending Instagram reply | comment_id={comment_id} | message_length={len(message)} | "
            f"message_preview={message[:50]}"
        )

        try:
            allowed, delay = await self._reply_rate_limiter.acquire()
            if not allowed:
                logger.warning(
                    f"Instagram reply deferred due to rate limit | comment_id={comment_id} | retry_after={delay:.2f}s"
                )
                return {
                    "success": False,
                    "status": "rate_limited",
                    "retry_after": float(delay),
                    "error": "Instagram rate limit reached",
                }

            session = await self._get_session()
            async with session.post(url, params=params) as response:
                response_data = await response.json()

                if response.status == 200:
                    reply_id = response_data.get("id") if isinstance(response_data, dict) else None
                    logger.info(
                        f"Instagram reply sent successfully | comment_id={comment_id} | "
                        f"reply_id={reply_id} | status_code={response.status}"
                    )
                    return {
                        "success": True,
                        "response": response_data,
                        "reply_id": reply_id,
                        "status_code": response.status,
                    }
                else:
                    error_data = response_data.get("error", {}) if isinstance(response_data, dict) else {}
                    if (
                        isinstance(error_data, dict)
                        and error_data.get("code") == 2
                        and "retry" in error_data.get("message", "").lower()
                    ):
                        logger.warning(
                            f"Instagram API rate limit response | comment_id={comment_id} | "
                            f"status_code={response.status} | will_retry=true"
                        )
                    else:
                        logger.error(
                            f"Instagram reply failed | comment_id={comment_id} | "
                            f"status_code={response.status} | error={response_data}"
                        )
                    return {
                        "success": False,
                        "error": response_data,
                        "status_code": response.status,
                    }

        except Exception as e:
            logger.error(
                f"Instagram reply exception | comment_id={comment_id} | error={str(e)}",
                exc_info=True
            )
            return {"success": False, "error": str(e), "status_code": None}

    async def get_comment_info(self, comment_id: str) -> Dict[str, Any]:
        """
        Get information about an Instagram comment.

        Args:
            comment_id: The ID of the Instagram comment

        Returns:
            Dict containing comment information
        """
        url = f"{self.base_url}/{comment_id}"
        params = {
            "access_token": self.access_token,
            "fields": "id,text,from,created_time,parent_id",
        }

        logger.debug(f"Getting comment info | comment_id={comment_id}")

        try:
            session = await self._get_session()
            async with session.get(url, params=params) as response:
                response_data = await response.json()

                if response.status == 200:
                    logger.info(
                        f"Comment info retrieved | comment_id={comment_id} | status_code={response.status}"
                    )
                    return {
                        "success": True,
                        "comment_info": response_data,
                        "status_code": response.status,
                    }
                else:
                    logger.error(
                        f"Failed to get comment info | comment_id={comment_id} | "
                        f"status_code={response.status} | error={response_data}"
                    )
                    return {
                        "success": False,
                        "error": response_data,
                        "status_code": response.status,
                    }

        except Exception as e:
            logger.error(
                f"Comment info exception | comment_id={comment_id} | error={str(e)}",
                exc_info=True
            )
            return {"success": False, "error": str(e), "status_code": None}

    async def validate_token(self) -> Dict[str, Any]:
        """
        Validate the Instagram access token.

        Returns:
            Dict containing validation result
        """
        try:
            status_code, response_data = await self._fetch_debug_token()
            logger.debug(f"Token validation response status: {status_code}")
            logger.debug(f"Token validation response: {response_data}")

            if status_code == 200:
                logger.info("Instagram access token is valid")
                return {
                    "success": True,
                    "token_info": response_data,
                    "status_code": status_code,
                }

            logger.error(f"Instagram access token validation failed: {response_data}")
            return {
                "success": False,
                "error": response_data,
                "status_code": status_code,
            }

        except Exception as e:
            logger.exception("Exception while validating Instagram token")
            return {"success": False, "error": str(e), "status_code": None}

    async def get_token_expiration(self) -> Dict[str, Any]:
        """
        Retrieve token expiration metadata (expires_at, seconds remaining).

        Returns:
            Dict with success flag, expires_at (datetime | None), expires_in (seconds | None)
        """
        try:
            status_code, response_data = await self._fetch_debug_token()
            if status_code != 200:
                logger.error(f"Failed to fetch token expiration metadata: {response_data}")
                return {
                    "success": False,
                    "error": response_data,
                    "status_code": status_code,
                }

            token_data = response_data.get("data", response_data)
            expires_at_timestamp = token_data.get("expires_at")
            expires_in_seconds = token_data.get("expires_in")

            expires_at_datetime: Optional[datetime] = None
            seconds_remaining: Optional[int] = None

            now = datetime.now(timezone.utc)

            if isinstance(expires_at_timestamp, (int, float)):
                expires_at_datetime = datetime.fromtimestamp(expires_at_timestamp, tz=timezone.utc)
            elif isinstance(expires_in_seconds, (int, float)):
                expires_at_datetime = now + timedelta(seconds=float(expires_in_seconds))

            if expires_at_datetime:
                seconds_remaining = max(int((expires_at_datetime - now).total_seconds()), 0)
            elif isinstance(expires_in_seconds, (int, float)):
                seconds_remaining = max(int(expires_in_seconds), 0)

            logger.info(
                "Fetched Instagram token expiration metadata | expires_at=%s | seconds_remaining=%s",
                expires_at_datetime.isoformat() if expires_at_datetime else None,
                seconds_remaining,
            )

            return {
                "success": True,
                "expires_at": expires_at_datetime,
                "expires_in": seconds_remaining,
                "status_code": status_code,
                "raw": token_data,
            }

        except Exception as exc:
            logger.exception("Exception while fetching Instagram token expiration metadata")
            return {"success": False, "error": str(exc), "status_code": None}

    async def get_media_info(self, media_id: str) -> Dict[str, Any]:
        """
        Get information about an Instagram media post.

        Args:
            media_id: The ID of the Instagram media post

        Returns:
            Dict containing media information
        """
        url = f"{self.base_url}/{media_id}"
        params = {
            "access_token": self.access_token,
            "fields": "permalink,comments_count,like_count,shortcode,timestamp,is_comment_enabled,media_type,media_url,username,owner,caption,children{media_url,media_type}",
        }

        logger.debug(f"Getting media info | media_id={media_id}")

        try:
            session = await self._get_session()
            async with session.get(url, params=params) as response:
                response_data = await response.json()

                if response.status == 200:
                    media_type = response_data.get("media_type", "unknown")
                    logger.info(
                        f"Media info retrieved | media_id={media_id} | media_type={media_type} | "
                        f"status_code={response.status}"
                    )
                    return {
                        "success": True,
                        "media_info": response_data,
                        "status_code": response.status,
                    }
                else:
                    logger.error(
                        f"Failed to get media info | media_id={media_id} | "
                        f"status_code={response.status} | error={response_data}"
                    )
                    return {
                        "success": False,
                        "error": response_data,
                        "status_code": response.status,
                    }

        except Exception as e:
            logger.error(
                f"Media info exception | media_id={media_id} | error={str(e)}",
                exc_info=True
            )
            return {"success": False, "error": str(e), "status_code": None}

    async def get_page_info(self) -> Dict[str, Any]:
        """
        Get Instagram page information.

        Returns:
            Dict containing page information
        """
        url = f"{self.base_url}/me"
        params = {"access_token": self.access_token, "fields": "id,name,username"}

        try:
            logger.debug(f"Getting page info with URL: {url}")

            session = await self._get_session()
            async with session.get(url, params=params) as response:
                response_data = await response.json()

                logger.debug(f"Page info response status: {response.status}")
                logger.debug(f"Page info response: {response_data}")

                if response.status == 200:
                    logger.info("Successfully retrieved page info")
                    return {
                        "success": True,
                        "page_info": response_data,
                        "status_code": response.status,
                    }
                else:
                    logger.error(f"Failed to get page info: {response_data}")
                    return {
                        "success": False,
                        "error": response_data,
                        "status_code": response.status,
                    }

        except Exception as e:
            logger.exception("Exception while getting page info")
            return {"success": False, "error": str(e), "status_code": None}

    async def set_media_comment_status(self, media_id: str, enabled: bool) -> Dict[str, Any]:
        """Enable or disable comments for a specific media item."""
        url = f"{self.base_url}/{media_id}"
        params = {
            "access_token": self.access_token,
            "comment_enabled": str(enabled).lower(),
        }

        action = "Enabling" if enabled else "Disabling"
        logger.info(f"{action} comments | media_id={media_id} | enabled={enabled}")

        try:
            session = await self._get_session()
            async with session.post(url, params=params) as response:
                response_data = await response.json()

                if response.status == 200:
                    logger.info(
                        f"Comment status updated | media_id={media_id} | enabled={enabled} | status_code={response.status}"
                    )
                    return {
                        "success": True,
                        "status_code": response.status,
                        "response": response_data,
                    }

                logger.error(
                    f"Failed to update comment status | media_id={media_id} | status_code={response.status} | error={response_data}"
                )
                return {
                    "success": False,
                    "status_code": response.status,
                    "error": response_data,
                }

        except Exception as exc:
            logger.error(
                f"Comment status update exception | media_id={media_id} | error={str(exc)}",
                exc_info=True,
            )
            return {"success": False, "error": str(exc), "status_code": None}

    async def hide_comment(self, comment_id: str, hide: bool = True) -> Dict[str, Any]:
        """
        Hide or unhide an Instagram comment.

        Note: Comments from media owners to their own media will always be shown.
        Live video comments are not supported.

        Args:
            comment_id: The ID of the Instagram comment to hide/unhide
            hide: True to hide the comment, False to unhide (default: True)

        Returns:
            Dict containing success status, response data, and status code
        """
        url = f"{self.base_url}/{comment_id}"
        params = {"access_token": self.access_token, "hide": str(hide).lower()}

        action = "Hiding" if hide else "Unhiding"
        logger.info(
            "%s comment | comment_id=%s | hide=%s",
            action,
            comment_id,
            hide,
        )

        try:
            session = await self._get_session()
            async with session.post(url, params=params) as response:
                response_data = await response.json()

                if response.status == 200:
                    action_past = "hidden" if hide else "unhidden"
                    logger.info(
                        "Comment %s successfully | comment_id=%s | status_code=%s | response=%s",
                        action_past,
                        comment_id,
                        response.status,
                        response_data,
                    )
                    return {
                        "success": True,
                        "response": response_data,
                        "status_code": response.status,
                    }
                else:
                    logger.error(
                        "Failed to %s comment | comment_id=%s | status_code=%s | error=%s",
                        action.lower(),
                        comment_id,
                        response.status,
                        response_data,
                    )
                    return {
                        "success": False,
                        "error": response_data,
                        "status_code": response.status,
                    }

        except Exception as e:
            logger.error(
                "Exception while %s comment | comment_id=%s | error=%s",
                action.lower(),
                comment_id,
                str(e),
                exc_info=True,
            )
            return {"success": False, "error": str(e), "status_code": None}

    async def _fetch_debug_token(self) -> Tuple[int, Dict[str, Any]]:
        """Fetch token debug information from Facebook Graph API."""
        debug_access_token = self._build_debug_access_token()

        url = f"https://graph.facebook.com/{settings.instagram.api_version}/debug_token"
        params = {
            "input_token": self.access_token,
            "access_token": debug_access_token,
        }

        logger.debug("Fetching token debug info | url=%s", url)

        session = await self._get_session()
        async with session.get(url, params=params) as response:
            response_data = await response.json()
            return response.status, response_data

    def _build_debug_access_token(self) -> str:
        """
        Build the app-level access token used for /debug_token requests.

        Priority:
            1. Explicit INSTAGRAM_APP_ACCESS_TOKEN
            2. Derived from INSTAGRAM_APP_ID and INSTAGRAM_APP_SECRET

        Raises:
            ValueError if neither option is configured.
        """
        if settings.instagram.app_access_token:
            return settings.instagram.app_access_token

        app_id = settings.instagram.app_id
        app_secret = settings.instagram.app_secret

        if app_id and app_secret:
            return f"{app_id}|{app_secret}"

        raise ValueError(
            "Instagram app credentials missing. Configure INSTAGRAM_APP_ACCESS_TOKEN or both "
            "INSTAGRAM_APP_ID and INSTAGRAM_APP_SECRET to enable token expiration checks."
        )

    async def delete_comment_reply(self, reply_id: str) -> Dict[str, Any]:
        """Delete an Instagram reply/comment by ID."""
        url = f"{self.base_url}/{reply_id}"
        params = {"access_token": self.access_token}

        logger.info(f"Deleting Instagram reply | reply_id={reply_id}")

        try:
            session = await self._get_session()
            async with session.delete(url, params=params) as response:
                response_data = await response.json()

                if response.status == 200:
                    logger.info(f"Instagram reply deleted | reply_id={reply_id}")
                    return {"success": True, "status_code": response.status, "response": response_data}

                logger.error(
                    f"Failed to delete Instagram reply | reply_id={reply_id} | status_code={response.status} | error={response_data}"
                )
                return {"success": False, "status_code": response.status, "error": response_data}
        except Exception as exc:
            logger.exception(f"Exception while deleting reply {reply_id}")
            return {"success": False, "error": str(exc), "status_code": None}
