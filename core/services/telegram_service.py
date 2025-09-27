"""
Telegram Notification Service

This module handles sending urgent issue notifications to Telegram chat
when Instagram comments are classified as urgent issues or complaints.
"""

import logging
import requests
from typing import Dict, Any, Optional
from ..config import settings

logger = logging.getLogger(__name__)

class TelegramService:
    """Service for sending notifications to Telegram"""
    
    def __init__(self, bot_token: str = None, chat_id: str = None):
        self.bot_token = bot_token or settings.telegram.bot_token
        self.chat_id = chat_id or settings.telegram.chat_id
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
    
    def send_urgent_issue_notification(self, comment_data: Dict[str, Any]) -> Dict[str, Any]:
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
            response = self._send_message(message)
            
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
        
        # Create formatted message
        message = f"""🚨 *URGENT ISSUE DETECTED* 🚨

📱 *Instagram Comment Alert*

👤 *User:* @{username}
🆔 *Comment ID:* `{comment_id}`
📸 *Media ID:* `{media_id}`
⏰ *Time:* {timestamp}

💬 *Comment Text:*
```
{comment_text}
```

🤖 *AI Analysis:*
• *Classification:* {classification}
• *Confidence:* {confidence}%
• *Sentiment:* {sentiment_score}/100
• *Toxicity:* {toxicity_score}/100

🧠 *AI Reasoning:*
{reasoning}

⚠️ *Action Required:* This comment has been classified as an urgent issue or complaint that requires immediate attention.

#urgent #instagram #complaint #customer_service"""

        return message
    
    def _send_message(self, message: str, parse_mode: str = "Markdown") -> Dict[str, Any]:
        """Send message to Telegram chat"""
        
        url = f"{self.base_url}/sendMessage"
        
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": parse_mode,
        }
        
        try:
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            return {"ok": False, "description": str(e)}
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return {"ok": False, "description": str(e)}
    
    def test_connection(self) -> Dict[str, Any]:
        """Test Telegram bot connection"""
        try:
            if not self.bot_token or not self.chat_id:
                return {
                    "success": False,
                    "error": "Bot token or chat ID not configured"
                }
            
            url = f"{self.base_url}/getMe"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            bot_info = response.json()
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
                
        except Exception as e:
            logger.error(f"Error testing Telegram connection: {e}")
            return {
                "success": False,
                "error": str(e)
            }

# Convenience function to get a pre-configured service
def get_telegram_service() -> TelegramService:
    """Get a pre-configured Telegram service using default settings"""
    return TelegramService()
