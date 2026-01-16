import inspect
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, Protocol, Tuple, Callable

import aiohttp
from aiolimiter import AsyncLimiter
from sqlalchemy.ext.asyncio import async_sessionmaker

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
        token_service_factory: Optional[Callable[..., Any]] = None,
        session_factory: Optional[Callable[..., Any]] = None,
    ):
        self._explicit_access_token = access_token
        self.access_token = access_token
        self.base_url = f"https://graph.instagram.com/{settings.instagram.api_version}"
        self._enabled = bool(self.access_token)
        self.token_service_factory = token_service_factory
        self.session_factory = session_factory
        self._account_id: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

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

    @staticmethod
    def _normalize_expires_at(value: Optional[datetime]) -> Optional[datetime]:
        if not value:
            return None
        if value.tzinfo:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    @classmethod
    def _is_expired(cls, value: Optional[datetime]) -> bool:
        if not value:
            return False
        normalized = cls._normalize_expires_at(value)
        return normalized <= datetime.utcnow()

    async def _load_tokens(self) -> Optional[Dict[str, Any]]:
        """Load Instagram tokens from secure storage if configured."""
        if not self.token_service_factory or not self.session_factory:
            return None
        try:
            session_factory = self.session_factory
            factory_result = session_factory() if callable(session_factory) else session_factory

            if isinstance(factory_result, async_sessionmaker):
                session_cm = factory_result()
            else:
                session_cm = factory_result

            async with session_cm as session:  # type: ignore
                token_service = self.token_service_factory(session=session)
                return await token_service.get_tokens("instagram", self._account_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load stored Instagram tokens | error=%s", exc)
            return None

    async def _require_access_token(self, operation: str) -> Optional[Dict[str, Any]]:
        if self._explicit_access_token:
            self.access_token = self._explicit_access_token
            return None

        if self.token_service_factory and self.session_factory:
            tokens = await self._load_tokens()
            if tokens:
                access_token = tokens.get("access_token")
                if not access_token:
                    logger.warning("Instagram token payload missing access_token | operation=%s", operation)
                    return {
                        "success": False,
                        "error": "Instagram access token is missing from storage",
                        "status_code": 400,
                        "error_code": "missing_access_token",
                        "operation": operation,
                    }

                expires_at = tokens.get("access_token_expires_at") or tokens.get("expires_at")
                if self._is_expired(expires_at):
                    normalized = self._normalize_expires_at(expires_at)
                    logger.warning(
                        "Instagram access token expired | operation=%s | expires_at=%s",
                        operation,
                        normalized.isoformat() if normalized else None,
                    )
                    return {
                        "success": False,
                        "error": "Instagram access token has expired; reconnect Instagram to continue.",
                        "status_code": 401,
                        "error_code": "access_token_expired",
                        "operation": operation,
                        "expires_at": normalized.isoformat() if normalized else None,
                    }

                self.access_token = access_token
                self._token_expires_at = self._normalize_expires_at(expires_at)
                account_id = tokens.get("account_id")
                if account_id:
                    self._account_id = account_id
                return None
            if self.access_token and not self._is_expired(self._token_expires_at):
                return None

        if self.access_token:
            return None

        logger.warning(
            "Instagram service disabled: missing access token | operation=%s",
            operation,
        )
        return {
            "success": False,
            "error": "Instagram access token is not configured; sync tokens via /api/v1/oauth/tokens",
            "status_code": 400,
            "error_code": "missing_access_token",
            "operation": operation,
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                connector=aiohttp.TCPConnector(limit=100, limit_per_host=30),
                headers={"Accept-Encoding": "gzip, deflate"},
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
        if error := await self._require_access_token("send_reply_to_comment"):
            return error

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
        if error := await self._require_access_token("get_comment_info"):
            return error

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
        if error := await self._require_access_token("validate_token"):
            return error

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
        if error := await self._require_access_token("get_token_expiration"):
            return error

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

        except ValueError as exc:
            logger.warning("Skipping token expiration check: %s", exc)
            return {
                "success": False,
                "error": str(exc),
                "status_code": 400,
                "error_code": "missing_app_credentials",
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
        if error := await self._require_access_token("get_media_info"):
            return error

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

    async def get_insights(self, account_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch insights from Instagram Graph API for the given account."""
        if error := await self._require_access_token("get_insights"):
            return error

        if not account_id:
            raise ValueError("Instagram account ID is required for insights")

        url = f"{self.base_url}/{account_id}/insights"
        query = {"access_token": self.access_token, **params}

        try:
            session = await self._get_session()
            async with session.get(url, params=query) as response:
                response_data = await response.json()

                if response.status == 200:
                    logger.debug(
                        "Instagram insights fetched | account_id=%s | params=%s",
                        account_id,
                        params,
                    )
                    return {
                        "success": True,
                        "data": response_data,
                        "status_code": response.status,
                    }

                logger.error(
                    "Failed to fetch Instagram insights | account_id=%s | status=%s | error=%s",
                    account_id,
                    response.status,
                    response_data,
                )
                return {
                    "success": False,
                    "error": response_data,
                    "status_code": response.status,
                }
        except Exception as exc:
            logger.exception("Error fetching Instagram insights | account_id=%s", account_id)
            return {"success": False, "error": str(exc), "status_code": None}

    async def get_page_info(self) -> Dict[str, Any]:
        """
        Get Instagram page information.

        Returns:
            Dict containing page information
        """
        if error := await self._require_access_token("get_page_info"):
            return error

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

    async def get_account_profile(self, account_id: Optional[str] = None) -> Dict[str, Any]:
        """Fetch account profile information: username, media_count, followers, follows."""
        if error := await self._require_access_token("get_account_profile"):
            return error

        target_id = account_id or self._account_id
        if not target_id:
            return {"success": False, "error": "Missing Instagram account ID", "status_code": 400}

        url = f"{self.base_url}/{target_id}"
        params = {
            "access_token": self.access_token,
            "fields": "username,media_count,followers_count,follows_count",
        }

        try:
            session = await self._get_session()
            async with session.get(url, params=params) as response:
                response_data = await response.json()

                if response.status == 200:
                    logger.info("Instagram account profile fetched | account_id=%s", target_id)
                    return {
                        "success": True,
                        "data": response_data,
                        "status_code": response.status,
                    }

                logger.error(
                    "Failed to fetch Instagram account profile | account_id=%s | status=%s | error=%s",
                    target_id,
                    response.status,
                    response_data,
                )
                return {
                    "success": False,
                    "error": response_data,
                    "status_code": response.status,
                }
        except Exception as exc:
            logger.exception("Error fetching Instagram account profile | account_id=%s", target_id)
            return {"success": False, "error": str(exc), "status_code": None}

    async def set_media_comment_status(self, media_id: str, enabled: bool) -> Dict[str, Any]:
        """Enable or disable comments for a specific media item."""
        if error := await self._require_access_token("set_media_comment_status"):
            return error

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
        if error := await self._require_access_token("hide_comment"):
            return error

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

    async def delete_comment(self, comment_id: str, *, resource_type: str = "comment") -> Dict[str, Any]:
        """Delete an Instagram comment or reply by ID."""
        if error := await self._require_access_token("delete_comment"):
            return error

        url = f"{self.base_url}/{comment_id}"
        params = {"access_token": self.access_token}

        logger.info(
            "Deleting Instagram %s | id=%s",
            resource_type,
            comment_id,
        )

        try:
            session = await self._get_session()
            async with session.delete(url, params=params) as response:
                response_data = await response.json()

                if response.status == 200:
                    logger.info(
                        "Instagram %s deleted | id=%s | status_code=%s | response=%s",
                        resource_type,
                        comment_id,
                        response.status,
                        response_data,
                    )
                    return {"success": True, "status_code": response.status, "response": response_data}

                logger.error(
                    "Failed to delete Instagram %s | id=%s | status_code=%s | error=%s",
                    resource_type,
                    comment_id,
                    response.status,
                    response_data,
                )
                return {"success": False, "status_code": response.status, "error": response_data}

        except Exception as exc:
            logger.exception("Exception while deleting Instagram %s | id=%s", resource_type, comment_id)
            return {"success": False, "error": str(exc), "status_code": None}

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
        return await self.delete_comment(reply_id, resource_type="reply")
