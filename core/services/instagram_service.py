
import asyncio
import aiohttp
import logging
from typing import Dict, Any, Optional
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
        
        # Log token info for debugging (without exposing the actual token)
        logger.info(f"Instagram service initialized with token: {self.access_token[:10]}...{self.access_token[-4:] if len(self.access_token) > 14 else '***'}")
        logger.info(f"Base URL: {self.base_url}")
    
    async def send_reply_to_comment(self, comment_id: str, message: str) -> Dict[str, Any]:
        """
        Send a reply to an Instagram comment using Instagram Graph API
        
        Args:
            comment_id: The ID of the Instagram comment to reply to (from instagram_comments table)
            message: The message to send as a reply
            
        Returns:
            Dict containing the API response
        """
        # Use the Instagram Graph API endpoint for posting replies to comments
        # Match the working Postman request: POST https://graph.instagram.com/v23.0/{comment_id}/replies?message={message}
        url = f"{self.base_url}/{comment_id}/replies"
        
        # Instagram Graph API expects access_token as query parameter and message in the URL
        params = {
            "access_token": self.access_token,
            "message": message
        }
        
        try:
            logger.info(f"Sending reply to comment {comment_id} with URL: {url}")
            logger.info(f"Request params: {params}")
            
            async with aiohttp.ClientSession() as session:
                # Use POST request with query parameters to match your working Postman request
                async with session.post(url, params=params) as response:
                    response_data = await response.json()
                    
                    logger.info(f"Response status: {response.status}")
                    logger.info(f"Response data: {response_data}")
                    
                    if response.status == 200:
                        logger.info(f"Successfully sent reply to comment {comment_id}")
                        # Extract reply_id from response to prevent infinite loops
                        reply_id = response_data.get("id") if isinstance(response_data, dict) else None
                        logger.info(f"Extracted reply_id: {reply_id} from response: {response_data}")
                        return {
                            "success": True,
                            "response": response_data,
                            "reply_id": reply_id,
                            "status_code": response.status
                        }
                    else:
                        logger.error(f"Failed to send reply to comment {comment_id}: {response_data}")
                        return {
                            "success": False,
                            "error": response_data,
                            "status_code": response.status
                        }
                        
        except Exception as e:
            logger.error(f"Exception while sending reply to comment {comment_id}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {
                "success": False,
                "error": str(e),
                "status_code": None
            }
    
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
            "fields": "id,text,from,created_time,parent_id"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    response_data = await response.json()
                    
                    if response.status == 200:
                        return {
                            "success": True,
                            "comment_info": response_data,
                            "status_code": response.status
                        }
                    else:
                        logger.error(f"Failed to get comment info for {comment_id}: {response_data}")
                        return {
                            "success": False,
                            "error": response_data,
                            "status_code": response.status
                        }
                        
        except Exception as e:
            logger.error(f"Exception while getting comment info for {comment_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "status_code": None
            }
    
    async def validate_token(self) -> Dict[str, Any]:
        """
        Validate the Instagram access token using Instagram Graph API debug endpoint
        
        Returns:
            Dict containing validation result
        """
        # Use Instagram Graph API debug endpoint to validate token
        url = f"https://graph.facebook.com/{settings.instagram.api_version}/debug_token"
        
        params = {
            "input_token": self.access_token,
            "access_token": self.access_token
        }
        
        try:
            logger.info(f"Validating Instagram token with URL: {url}")
            logger.info(f"Token: {self.access_token[:10]}...{self.access_token[-4:] if len(self.access_token) > 14 else '***'}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    response_data = await response.json()
                    
                    logger.info(f"Token validation response status: {response.status}")
                    logger.info(f"Token validation response: {response_data}")
                    
                    if response.status == 200:
                        logger.info("Instagram access token is valid")
                        return {
                            "success": True,
                            "token_info": response_data,
                            "status_code": response.status
                        }
                    else:
                        logger.error(f"Instagram access token validation failed: {response_data}")
                        return {
                            "success": False,
                            "error": response_data,
                            "status_code": response.status
                        }
                        
        except Exception as e:
            logger.error(f"Exception while validating Instagram token: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {
                "success": False,
                "error": str(e),
                "status_code": None
            }
    
    async def get_page_info(self) -> Dict[str, Any]:
        """
        Get Instagram page information using the access token
        
        Returns:
            Dict containing page information
        """
        url = f"{self.base_url}/me"
        
        params = {
            "access_token": self.access_token,
            "fields": "id,name,username"
        }
        
        try:
            logger.info(f"Getting page info with URL: {url}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    response_data = await response.json()
                    
                    logger.info(f"Page info response status: {response.status}")
                    logger.info(f"Page info response: {response_data}")
                    
                    if response.status == 200:
                        logger.info("Successfully retrieved page info")
                        return {
                            "success": True,
                            "page_info": response_data,
                            "status_code": response.status
                        }
                    else:
                        logger.error(f"Failed to get page info: {response_data}")
                        return {
                            "success": False,
                            "error": response_data,
                            "status_code": response.status
                        }
                        
        except Exception as e:
            logger.error(f"Exception while getting page info: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {
                "success": False,
                "error": str(e),
                "status_code": None
            }
