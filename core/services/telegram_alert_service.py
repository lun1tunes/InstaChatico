"""
Telegram Notification Service

This module handles sending urgent issue notifications to Telegram chat
when Instagram comments are classified as urgent issues or complaints.
"""

import logging
from typing import Any, Dict

import aiohttp

from ..config import settings

logger = logging.getLogger(__name__)

class TelegramAlertService:
    """Service for sending alert notifications to Telegram"""
    
    def __init__(self, bot_token: str = None, chat_id: str = None):
        self.bot_token = bot_token or settings.telegram.bot_token
        self.chat_id = chat_id or settings.telegram.chat_id
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
    
    async def send_urgent_issue_notification(self, comment_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send urgent issue notification to Telegram
        
        Args:
            comment_data: Dictionary containing comment information
            
        Returns:
            Dictionary with success status and response details
        """
        try:
            if not self.bot_token or not self.chat_id:
                logger.error("Telegram bot token or chat ID not configured")
                return {
                    "success": False,
                    "error": "Telegram configuration missing"
                }
            
            # Format the message
            message = self._format_urgent_message(comment_data)
            
            # Send message to Telegram
            response = await self._send_message(message)
            
            if response.get("ok"):
                logger.info(f"Urgent issue notification sent successfully for comment {comment_data.get('comment_id', 'unknown')}")
                return {
                    "success": True,
                    "message_id": response.get("result", {}).get("message_id"),
                    "response": response
                }
            else:
                logger.error(f"Failed to send Telegram notification: {response}")
                return {
                    "success": False,
                    "error": response.get("description", "Unknown error"),
                    "response": response
                }
                
        except Exception as e:
            logger.error(f"Error sending Telegram notification: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _format_urgent_message(self, comment_data: Dict[str, Any]) -> str:
        """Format the urgent issue message for Telegram"""
        
        # Extract data with fallbacks
        comment_id = comment_data.get('comment_id', 'Unknown')
        comment_text = comment_data.get('comment_text', 'No text available')
        classification = comment_data.get('classification', 'Unknown')
        confidence = comment_data.get('confidence', 0)
        reasoning = comment_data.get('reasoning', 'No reasoning provided')
        sentiment_score = comment_data.get('sentiment_score', 0)
        toxicity_score = comment_data.get('toxicity_score', 0)
        media_id = comment_data.get('media_id', 'Unknown')
        username = comment_data.get('username', 'Unknown user')
        timestamp = comment_data.get('timestamp', 'Unknown time')
        
        # Create formatted message with HTML formatting (more reliable than Markdown)
        def escape_html(text: str) -> str:
            if not text:
                return ""
            # Escape HTML special characters
            return (text.replace("&", "&amp;")
                     .replace("<", "&lt;")
                     .replace(">", "&gt;")
                     .replace('"', "&quot;")
                     .replace("'", "&#x27;"))
        
        # Escape HTML special characters
        html_username = escape_html(username)
        html_comment_id = escape_html(comment_id)
        html_media_id = escape_html(media_id)
        html_timestamp = escape_html(timestamp)
        html_classification = escape_html(classification)
        html_comment_text = escape_html(comment_text)
        html_reasoning = escape_html(reasoning)
        
        # Truncate very long messages to avoid Telegram limits
        if len(html_comment_text) > 1000:
            html_comment_text = html_comment_text[:997] + "..."
        
        if len(html_reasoning) > 500:
            html_reasoning = html_reasoning[:497] + "..."
        
        message = f"""🚨 <b>URGENT ISSUE DETECTED</b> 🚨

📱 <b>Instagram Comment Alert</b>

👤 <b>Instagram Username:</b> {html_username}
⏰ <b>Time:</b> {html_timestamp}
🆔 <b>Comment ID:</b> <code>{html_comment_id}</code>
📸 <b>Media ID:</b> <code>{html_media_id}</code>

💬 <b>Comment Text:</b>
<pre>{html_comment_text}</pre>

🤖 <b>AI Analysis:</b>
• <b>Classification:</b> {html_classification}
• <b>Confidence:</b> {confidence}%
• <b>Sentiment:</b> {sentiment_score}/100
• <b>Toxicity:</b> {toxicity_score}/100

🧠 <b>AI Reasoning:</b>
{html_reasoning}

⚠️ <b>Action Required:</b> This comment has been classified as an urgent issue or complaint that requires immediate attention.

#urgent #instagram #complaint #customer_service"""

        return message
    
    async def _send_message(self, message: str, parse_mode: str = "HTML") -> Dict[str, Any]:
        """Send message to Telegram chat using aiohttp"""
        
        url = f"{self.base_url}/sendMessage"
        
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        logger.error(f"Telegram API error {response.status}: {error_text}")
                        return {"ok": False, "description": f"HTTP {response.status}: {error_text}"}
        except aiohttp.ClientError as e:
            logger.error(f"aiohttp request failed: {e}")
            return {"ok": False, "description": str(e)}
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return {"ok": False, "description": str(e)}
    
    async def test_connection(self) -> Dict[str, Any]:
        """Test Telegram bot connection using aiohttp"""
        try:
            if not self.bot_token or not self.chat_id:
                return {
                    "success": False,
                    "error": "Bot token or chat ID not configured"
                }
            
            url = f"{self.base_url}/getMe"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        bot_info = await response.json()
                        if bot_info.get("ok"):
                            return {
                                "success": True,
                                "bot_info": bot_info.get("result", {}),
                                "chat_id": self.chat_id
                            }
                        else:
                            return {
                                "success": False,
                                "error": bot_info.get("description", "Unknown error")
                            }
                    else:
                        error_text = await response.text()
                        return {
                            "success": False,
                            "error": f"HTTP {response.status}: {error_text}"
                        }
                
        except Exception as e:
            logger.error(f"Error testing Telegram connection: {e}")
            return {
                "success": False,
                "error": str(e)
            }

# Convenience function to get a pre-configured service
def get_telegram_service() -> TelegramAlertService:
    """Get a pre-configured Telegram alert service using default settings"""
    return TelegramAlertService()
