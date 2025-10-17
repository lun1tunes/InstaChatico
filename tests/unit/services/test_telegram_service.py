"""
Unit tests for TelegramAlertService.
"""

import pytest
from unittest.mock import AsyncMock, patch

from core.services.telegram_alert_service import TelegramAlertService


@pytest.mark.unit
@pytest.mark.service
class TestTelegramAlertService:
    """Test TelegramAlertService methods."""

    @patch("aiohttp.ClientSession")
    async def test_send_urgent_issue_notification_success(self, mock_session_class):
        """Test sending urgent issue notification."""
        # Arrange
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "ok": True,
            "result": {"message_id": 123}
        })

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session_class.return_value = mock_session

        service = TelegramAlertService(bot_token="test_token", chat_id="test_chat")

        comment_data = {
            "comment_id": "comment_123",
            "comment_text": "Urgentproblem!",
            "classification": "urgent issue / complaint",
            "confidence": 95,
            "reasoning": "Contains urgent complaint",
            "media_id": "media_123",
            "username": "user123",
            "timestamp": "2025-01-01 12:00:00"
        }

        # Act
        result = await service.send_urgent_issue_notification(comment_data)

        # Assert
        assert result["success"] is True
        assert result["message_id"] == 123
        mock_session.post.assert_called_once()

    @patch("aiohttp.ClientSession")
    async def test_send_critical_feedback_notification(self, mock_session_class):
        """Test sending critical feedback notification."""
        # Arrange
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "ok": True,
            "result": {"message_id": 456}
        })

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session_class.return_value = mock_session

        service = TelegramAlertService(bot_token="test_token", chat_id="test_chat")

        comment_data = {
            "comment_id": "comment_456",
            "comment_text": "Critical feedback",
            "classification": "critical feedback",
            "confidence": 90,
            "reasoning": "Important feedback",
            "media_id": "media_456",
            "username": "user456",
            "timestamp": "2025-01-01 12:00:00"
        }

        # Act
        result = await service.send_critical_feedback_notification(comment_data)

        # Assert
        assert result["success"] is True
        assert result["message_id"] == 456

    async def test_send_notification_missing_config(self):
        """Test notification fails with missing configuration."""
        # Arrange
        service = TelegramAlertService(bot_token=None, chat_id=None)
        comment_data = {"comment_id": "test"}

        # Act
        result = await service.send_urgent_issue_notification(comment_data)

        # Assert
        assert result["success"] is False
        assert "configuration missing" in result["error"].lower()

    @patch("aiohttp.ClientSession")
    async def test_send_notification_api_error(self, mock_session_class):
        """Test notification handles API error."""
        # Arrange
        mock_response = AsyncMock()
        mock_response.status = 400
        mock_response.json = AsyncMock(return_value={
            "ok": False,
            "description": "Bad request"
        })

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session_class.return_value = mock_session

        service = TelegramAlertService(bot_token="test_token", chat_id="test_chat")
        comment_data = {"comment_id": "test", "comment_text": "Test"}

        # Act
        result = await service.send_urgent_issue_notification(comment_data)

        # Assert
        assert result["success"] is False
        assert "Bad request" in result["error"]

    def test_escape_html(self):
        """Test HTML escaping."""
        # Arrange
        text_with_html = "<script>alert('test')</script>"

        # Act
        escaped = TelegramAlertService._escape_html(text_with_html)

        # Assert
        assert "&lt;" in escaped
        assert "&gt;" in escaped
        assert "<script>" not in escaped

    def test_prepare_message_data_truncates_long_text(self):
        """Test that long text is truncated."""
        # Arrange
        service = TelegramAlertService(bot_token="test", chat_id="test")
        long_text = "a" * 1500
        comment_data = {
            "comment_text": long_text,
            "reasoning": "b" * 600
        }

        # Act
        result = service._prepare_message_data(comment_data)

        # Assert
        assert len(result["comment_text"]) <= 1000
        assert result["comment_text"].endswith("...")
        assert len(result["reasoning"]) <= 500

    @patch("aiohttp.ClientSession")
    async def test_send_partnership_proposal_notification(self, mock_session_class):
        """Test sending partnership proposal notification."""
        # Arrange
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"ok": True, "result": {"message_id": 789}})

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session_class.return_value = mock_session

        service = TelegramAlertService(bot_token="test_token", chat_id="test_chat")
        comment_data = {
            "comment_id": "comment_789",
            "comment_text": "Partnership opportunity",
            "classification": "partnership proposal"
        }

        # Act
        result = await service.send_partnership_proposal_notification(comment_data)

        # Assert
        assert result["success"] is True
        assert result["message_id"] == 789

    @patch("aiohttp.ClientSession")
    async def test_send_log_alert(self, mock_session_class):
        """Test sending log alert."""
        # Arrange
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"ok": True, "result": {}})

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session_class.return_value = mock_session

        service = TelegramAlertService(bot_token="test_token", chat_id="test_chat")
        log_data = {
            "level": "ERROR",
            "message": "Test error",
            "logger": "test_logger",
            "trace_id": "trace_123"
        }

        # Act
        result = await service.send_log_alert(log_data)

        # Assert
        assert result["ok"] is True

    async def test_send_notification_routes_by_classification(self):
        """Test that send_notification routes to correct handler."""
        # Arrange
        service = TelegramAlertService(bot_token="test", chat_id="test")

        # Mock the specific handlers
        service.send_urgent_issue_notification = AsyncMock(return_value={"success": True})
        service.send_critical_feedback_notification = AsyncMock(return_value={"success": True})
        service.send_partnership_proposal_notification = AsyncMock(return_value={"success": True})

        # Act & Assert - urgent issue
        await service.send_notification({"classification": "urgent issue / complaint"})
        service.send_urgent_issue_notification.assert_called_once()

        # Act & Assert - critical feedback
        await service.send_notification({"classification": "critical feedback"})
        service.send_critical_feedback_notification.assert_called_once()

        # Act & Assert - partnership
        await service.send_notification({"classification": "partnership proposal"})
        service.send_partnership_proposal_notification.assert_called_once()
