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
        self.base_url = settings.instagram.base_url
        
        if not self.access_token:
            raise ValueError("Instagram access token is required")
    
    async def send_reply_to_comment(self, comment_id: str, message: str) -> Dict[str, Any]:
        """
        Send a reply to an Instagram comment using Graph API
        
        Args:
            comment_id: The ID of the Instagram comment to reply to (from instagram_comments table)
            message: The message to send as a reply
            
        Returns:
            Dict containing the API response
        """
        # Use the Instagram Graph API endpoint for posting replies to comments
        url = f"{self.base_url}/{comment_id}/replies"
        
        # Instagram Graph API expects form-encoded data
        data = {
            "message": message,
            "access_token": self.access_token
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data) as response:
                    response_data = await response.json()
                    
                    if response.status == 200:
                        logger.info(f"Successfully sent reply to comment {comment_id}")
                        return {
                            "success": True,
                            "response": response_data,
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
        Validate the Instagram access token
        
        Returns:
            Dict containing validation result
        """
        url = f"{self.base_url}/me"
        
        params = {
            "access_token": self.access_token,
            "fields": "id,name"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    response_data = await response.json()
                    
                    if response.status == 200:
                        logger.info("Instagram access token is valid")
                        return {
                            "success": True,
                            "page_info": response_data,
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
            return {
                "success": False,
                "error": str(e),
                "status_code": None
            }
