import logging
from typing import Any, Dict

import aiohttp

from ..config import settings

logger = logging.getLogger(__name__)


class InstagramGraphAPIService:
    """Service for interacting with Instagram Graph API"""

    def __init__(self, access_token: str = None):
        self.access_token = access_token or settings.instagram.access_token
        # Use graph.instagram.com instead of graph.facebook.com for Instagram API
        self.base_url = f"https://graph.instagram.com/{settings.instagram.api_version}"

        if not self.access_token:
            raise ValueError("Instagram access token is required")

    async def send_reply_to_comment(self, comment_id: str, message: str) -> Dict[str, Any]:
        """Send reply to Instagram comment via Graph API."""
        url = f"{self.base_url}/{comment_id}/replies"
        params = {"access_token": self.access_token, "message": message}

        logger.info(
            f"Sending Instagram reply | comment_id={comment_id} | message_length={len(message)} | "
            f"message_preview={message[:50]}"
        )

        try:
            async with aiohttp.ClientSession() as session:
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
                        # Check if it's a rate limiting error
                        error_data = response_data.get("error", {})
                        if (
                            error_data.get("code") == 2
                            and "retry" in error_data.get("message", "").lower()
                        ):
                            logger.warning(
                                f"Instagram API rate limit | comment_id={comment_id} | "
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
        Get information about an Instagram comment

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
            async with aiohttp.ClientSession() as session:
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
        Validate the Instagram access token using Instagram Graph API debug endpoint

        Returns:
            Dict containing validation result
        """
        # Use Instagram Graph API debug endpoint to validate token
        url = f"https://graph.facebook.com/{settings.instagram.api_version}/debug_token"

        params = {"input_token": self.access_token, "access_token": self.access_token}

        try:
            logger.debug(f"Validating Instagram token with URL: {url}")
            logger.debug(
                f"Token: {self.access_token[:10]}...{self.access_token[-4:] if len(self.access_token) > 14 else '***'}"
            )

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    response_data = await response.json()

                    logger.debug(f"Token validation response status: {response.status}")
                    logger.debug(f"Token validation response: {response_data}")

                    if response.status == 200:
                        logger.info("Instagram access token is valid")
                        return {
                            "success": True,
                            "token_info": response_data,
                            "status_code": response.status,
                        }
                    else:
                        logger.error(
                            f"Instagram access token validation failed: {response_data}"
                        )
                        return {
                            "success": False,
                            "error": response_data,
                            "status_code": response.status,
                        }

        except Exception as e:
            logger.exception("Exception while validating Instagram token")
            return {"success": False, "error": str(e), "status_code": None}

    async def get_media_info(self, media_id: str) -> Dict[str, Any]:
        """
        Get information about an Instagram media post

        Args:
            media_id: The ID of the Instagram media post

        Returns:
            Dict containing media information
        """
        url = f"{self.base_url}/{media_id}"

        # Include children{media_url,media_type} to get all images from CAROUSEL_ALBUM
        params = {
            "access_token": self.access_token,
            "fields": "permalink,comments_count,like_count,shortcode,timestamp,is_comment_enabled,media_type,media_url,username,owner,caption,children{media_url,media_type}",
        }

        logger.debug(f"Getting media info | media_id={media_id}")

        try:
            async with aiohttp.ClientSession() as session:
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
        Get Instagram page information using the access token

        Returns:
            Dict containing page information
        """
        url = f"{self.base_url}/me"

        params = {"access_token": self.access_token, "fields": "id,name,username"}

        try:
            logger.debug(f"Getting page info with URL: {url}")

            async with aiohttp.ClientSession() as session:
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

    async def hide_comment(self, comment_id: str, hide: bool = True) -> Dict[str, Any]:
        """
        Hide or unhide an Instagram comment via Graph API.

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
        logger.info(f"{action} comment | comment_id={comment_id} | hide={hide}")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, params=params) as response:
                    response_data = await response.json()

                    if response.status == 200:
                        action_past = "hidden" if hide else "unhidden"
                        logger.info(
                            f"Comment {action_past} successfully | comment_id={comment_id} | "
                            f"status_code={response.status}"
                        )
                        return {
                            "success": True,
                            "response": response_data,
                            "status_code": response.status,
                        }
                    else:
                        logger.error(
                            f"Failed to {action.lower()} comment | comment_id={comment_id} | "
                            f"status_code={response.status} | error={response_data}"
                        )
                        return {
                            "success": False,
                            "error": response_data,
                            "status_code": response.status,
                        }

        except Exception as e:
            logger.error(
                f"Exception while {action.lower()} comment | comment_id={comment_id} | error={str(e)}",
                exc_info=True
            )
            return {"success": False, "error": str(e), "status_code": None}
