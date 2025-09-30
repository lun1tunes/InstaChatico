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
    """Service for sending alert notifications to Telegram for urgent issues and critical feedback"""

    def __init__(
        self,
        bot_token: str = None,
        chat_id: str = None,
        alert_type: str = "instagram_comment_alerts",
    ):
        self.bot_token = bot_token or settings.telegram.bot_token
        self.chat_id = chat_id or settings.telegram.chat_id
        if alert_type == "instagram_comment_alerts":
            self.thread_id = settings.telegram.tg_chat_alerts_thread_id
        elif alert_type == "app_logs":
            self.thread_id = settings.telegram.tg_chat_logs_thread_id
        else:
            self.thread_id = None
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    async def send_urgent_issue_notification(
        self, comment_data: Dict[str, Any]
    ) -> Dict[str, Any]:
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
                return {"success": False, "error": "Telegram configuration missing"}

            # Format the message
            message = self._format_urgent_message(comment_data)

            # Send message to Telegram
            response = await self._send_message(message)

            if response.get("ok"):
                logger.info(
                    f"Urgent issue notification sent successfully for comment {comment_data.get('comment_id', 'unknown')}"
                )
                return {
                    "success": True,
                    "message_id": response.get("result", {}).get("message_id"),
                    "response": response,
                }
            else:
                logger.error(f"Failed to send Telegram notification: {response}")
                return {
                    "success": False,
                    "error": response.get("description", "Unknown error"),
                    "response": response,
                }

        except Exception as e:
            logger.exception("Error sending Telegram notification")
            return {"success": False, "error": str(e)}

    async def send_critical_feedback_notification(
        self, comment_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Send critical feedback notification to Telegram

        Args:
            comment_data: Dictionary containing comment information

        Returns:
            Dictionary with success status and response details
        """
        try:
            if not self.bot_token or not self.chat_id:
                logger.error("Telegram bot token or chat ID not configured")
                return {"success": False, "error": "Telegram configuration missing"}

            # Format the message
            message = self._format_critical_message(comment_data)

            # Send message to Telegram
            response = await self._send_message(message)

            if response.get("ok"):
                logger.info(
                    f"Critical feedback notification sent successfully for comment {comment_data.get('comment_id', 'unknown')}"
                )
                return {
                    "success": True,
                    "message_id": response.get("result", {}).get("message_id"),
                    "response": response,
                }
            else:
                logger.error(f"Failed to send Telegram notification: {response}")
                return {
                    "success": False,
                    "error": response.get("description", "Unknown error"),
                    "response": response,
                }

        except Exception as e:
            logger.exception("Error sending Telegram notification")
            return {"success": False, "error": str(e)}

    def _format_urgent_message(self, comment_data: Dict[str, Any]) -> str:
        """Format the urgent issue message for Telegram"""

        # Extract data with fallbacks
        comment_id = comment_data.get("comment_id", "Unknown")
        comment_text = comment_data.get("comment_text", "No text available")
        classification = comment_data.get("classification", "Unknown")
        confidence = comment_data.get("confidence", 0)
        reasoning = comment_data.get("reasoning", "No reasoning provided")
        sentiment_score = comment_data.get("sentiment_score", 0)
        toxicity_score = comment_data.get("toxicity_score", 0)
        media_id = comment_data.get("media_id", "Unknown")
        username = comment_data.get("username", "Unknown user")
        timestamp = comment_data.get("timestamp", "Unknown time")

        # Create formatted message with HTML formatting (more reliable than Markdown)
        def escape_html(text: str) -> str:
            if not text:
                return ""
            # Escape HTML special characters
            return (
                text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&#x27;")
            )

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

    def _format_critical_message(self, comment_data: Dict[str, Any]) -> str:
        """Format the critical feedback message for Telegram"""

        # Extract data with fallbacks
        comment_id = comment_data.get("comment_id", "Unknown")
        comment_text = comment_data.get("comment_text", "No text available")
        classification = comment_data.get("classification", "Unknown")
        confidence = comment_data.get("confidence", 0)
        reasoning = comment_data.get("reasoning", "No reasoning provided")
        sentiment_score = comment_data.get("sentiment_score", 0)
        toxicity_score = comment_data.get("toxicity_score", 0)
        media_id = comment_data.get("media_id", "Unknown")
        username = comment_data.get("username", "Unknown user")
        timestamp = comment_data.get("timestamp", "Unknown time")

        # Create formatted message with HTML formatting (more reliable than Markdown)
        def escape_html(text: str) -> str:
            if not text:
                return ""
            # Escape HTML special characters
            return (
                text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&#x27;")
            )

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

        message = f"""⚠️ <b>CRITICAL FEEDBACK DETECTED</b> ⚠️

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

📋 <b>Action Required:</b> This comment contains critical feedback that may require attention or follow-up.

#critical #instagram #feedback #customer_service"""

        return message

    async def send_notification(self, comment_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send appropriate notification based on comment classification

        Args:
            comment_data: Dictionary containing comment information

        Returns:
            Dictionary with success status and response details
        """
        classification = comment_data.get("classification", "").lower()

        if classification == "urgent issue / complaint":
            return await self.send_urgent_issue_notification(comment_data)
        elif classification == "critical feedback":
            return await self.send_critical_feedback_notification(comment_data)
        else:
            logger.warning(
                f"No notification needed for classification: {classification}"
            )
            return {
                "success": False,
                "error": f"No notification configured for classification: {classification}",
            }

    async def send_log_alert(self, log_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send application log alerts to Telegram LOGS thread with HTML formatting.
        Expects keys: level, logger, message, trace_id, timestamp, exception (optional)
        """
        try:
            if not self.bot_token or not self.chat_id:
                logger.error("Telegram bot token or chat ID not configured")
                return {"success": False, "error": "Telegram configuration missing"}

            level = str(log_data.get("level", "WARNING"))
            logger_name = str(log_data.get("logger", "-"))
            message = str(log_data.get("message", ""))
            trace_id = str(log_data.get("trace_id", "-"))
            timestamp = str(log_data.get("timestamp", ""))
            exception = log_data.get("exception", "")

            # HTML escape function
            def esc(text: str) -> str:
                return (
                    text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                )

            # Choose emoji based on level
            emoji_map = {
                "WARNING": "⚠️",
                "ERROR": "🔴",
                "CRITICAL": "🚨",
            }
            emoji = emoji_map.get(level, "ℹ️")

            # Format message with HTML for beautiful display
            safe_msg = esc(message)[:3500]
            safe_exception = esc(exception)[:3500] if exception else ""

            text_parts = [
                f"{emoji} <b>APP LOG ALERT</b>",
                f"<b>Level:</b> {esc(level)}",
                f"<b>Logger:</b> {esc(logger_name)}",
                f"<b>Trace:</b> <code>{esc(trace_id)}</code>",
                f"<b>Time:</b> {esc(timestamp)}",
                "",
                f"<b>Message:</b>",
                f"<pre>{safe_msg}</pre>",
            ]

            if safe_exception:
                text_parts.extend(
                    [
                        "",
                        f"<b>Details:</b>",
                        f"<pre>{safe_exception}</pre>",
                    ]
                )

            text = "\n".join(text_parts)

            # Telegram max message ~4096 chars
            if len(text) > 3900:
                # Truncate if too long
                if safe_exception:
                    safe_exception = safe_exception[:1500] + "..."
                safe_msg = safe_msg[:2000] + "..."
                text_parts = [
                    f"{emoji} <b>APP LOG ALERT</b>",
                    f"<b>Level:</b> {esc(level)}",
                    f"<b>Logger:</b> {esc(logger_name)}",
                    f"<b>Trace:</b> <code>{esc(trace_id)}</code>",
                    f"<b>Time:</b> {esc(timestamp)}",
                    "",
                    f"<b>Message:</b>",
                    f"<pre>{safe_msg}</pre>",
                ]
                if safe_exception:
                    text_parts.extend(
                        [
                            "",
                            f"<b>Details:</b>",
                            f"<pre>{safe_exception}</pre>",
                        ]
                    )
                text = "\n".join(text_parts)

            return await self._send_message(text, parse_mode="HTML")
        except Exception as e:
            logger.exception("Error sending log alert to Telegram")
            return {"success": False, "error": str(e)}

    async def _send_message(
        self, message: str, parse_mode: str | None = "HTML"
    ) -> Dict[str, Any]:
        """Send message to Telegram chat using aiohttp"""

        url = f"{self.base_url}/sendMessage"

        payload = {
            "chat_id": self.chat_id,
            "message_thread_id": self.thread_id,
            "text": message,
            "disable_web_page_preview": True,
        }

        if parse_mode:
            payload["parse_mode"] = parse_mode

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=payload, timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        logger.error(
                            f"Telegram API error {response.status}: {error_text}"
                        )
                        return {
                            "ok": False,
                            "description": f"HTTP {response.status}: {error_text}",
                        }
        except aiohttp.ClientError as e:
            logger.error(f"aiohttp request failed: {e}")
            return {"ok": False, "description": str(e)}
        except Exception as e:
            logger.exception("Unexpected error during Telegram API request")
            return {"ok": False, "description": str(e)}

    async def test_connection(self) -> Dict[str, Any]:
        """Test Telegram bot connection using aiohttp"""
        try:
            if not self.bot_token or not self.chat_id:
                return {
                    "success": False,
                    "error": "Bot token or chat ID not configured",
                }

            url = f"{self.base_url}/getMe"

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        bot_info = await response.json()
                        if bot_info.get("ok"):
                            return {
                                "success": True,
                                "bot_info": bot_info.get("result", {}),
                                "chat_id": self.chat_id,
                            }
                        else:
                            return {
                                "success": False,
                                "error": bot_info.get("description", "Unknown error"),
                            }
                    else:
                        error_text = await response.text()
                        return {
                            "success": False,
                            "error": f"HTTP {response.status}: {error_text}",
                        }

        except Exception as e:
            logger.exception("Error testing Telegram connection")
            return {"success": False, "error": str(e)}


# Convenience function to get a pre-configured service
def get_telegram_service() -> TelegramAlertService:
    """Get a pre-configured Telegram alert service using default settings"""
    return TelegramAlertService()
