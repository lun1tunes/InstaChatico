"""
Unit tests for InstagramGraphAPIService.
"""

import pytest
from unittest.mock import AsyncMock, patch

from core.services.instagram_service import InstagramGraphAPIService


@pytest.mark.unit
@pytest.mark.service
class TestInstagramGraphAPIService:
    """Test InstagramGraphAPIService methods."""

    @patch("aiohttp.ClientSession")
    async def test_send_reply_success(self, mock_session_class):
        """Test successful Instagram reply."""
        # Arrange
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"id": "reply_123"})

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session_class.return_value = mock_session

        service = InstagramGraphAPIService(access_token="test_token")

        # Act
        result = await service.send_reply_to_comment("comment_123", "Test reply")

        # Assert
        assert result["success"] is True
        assert result["reply_id"] == "reply_123"
        assert result["status_code"] == 200
        mock_session.post.assert_called_once()

    @patch("aiohttp.ClientSession")
    async def test_send_reply_failure(self, mock_session_class):
        """Test failed Instagram reply."""
        # Arrange
        mock_response = AsyncMock()
        mock_response.status = 400
        mock_response.json = AsyncMock(return_value={"error": {"message": "Bad request"}})

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session_class.return_value = mock_session

        service = InstagramGraphAPIService(access_token="test_token")

        # Act
        result = await service.send_reply_to_comment("comment_123", "Test reply")

        # Assert
        assert result["success"] is False
        assert result["status_code"] == 400

    @patch("aiohttp.ClientSession")
    async def test_send_reply_rate_limit(self, mock_session_class):
        """Test rate limit handling."""
        # Arrange
        mock_response = AsyncMock()
        mock_response.status = 429
        mock_response.json = AsyncMock(return_value={
            "error": {"code": 2, "message": "Please retry"}
        })

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session_class.return_value = mock_session

        service = InstagramGraphAPIService(access_token="test_token")

        # Act
        result = await service.send_reply_to_comment("comment_123", "Test reply")

        # Assert
        assert result["success"] is False
        assert result["status_code"] == 429

    @patch("aiohttp.ClientSession")
    async def test_hide_comment_success(self, mock_session_class):
        """Test hiding a comment."""
        # Arrange
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"success": True})

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session_class.return_value = mock_session

        service = InstagramGraphAPIService(access_token="test_token")

        # Act
        result = await service.hide_comment("comment_123", hide=True)

        # Assert
        assert result["success"] is True
        assert result["status_code"] == 200
        # Verify hide=true was passed
        call_args = mock_session.post.call_args
        assert "hide" in call_args.kwargs["params"]
        assert call_args.kwargs["params"]["hide"] == "true"

    @patch("aiohttp.ClientSession")
    async def test_unhide_comment(self, mock_session_class):
        """Test unhiding a comment."""
        # Arrange
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"success": True})

        mock_session = AsyncMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session_class.return_value = mock_session

        service = InstagramGraphAPIService(access_token="test_token")

        # Act
        result = await service.hide_comment("comment_123", hide=False)

        # Assert
        assert result["success"] is True
        call_args = mock_session.post.call_args
        assert call_args.kwargs["params"]["hide"] == "false"

    def test_service_requires_token(self):
        """Test that service requires access token."""
        # Act & Assert
        with pytest.raises(ValueError, match="Instagram access token is required"):
            InstagramGraphAPIService(access_token=None)

    @patch("aiohttp.ClientSession")
    async def test_exception_handling(self, mock_session_class):
        """Test exception handling during API calls."""
        # Arrange
        mock_session = AsyncMock()
        mock_session.post = AsyncMock(side_effect=Exception("Network error"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session_class.return_value = mock_session

        service = InstagramGraphAPIService(access_token="test_token")

        # Act
        result = await service.send_reply_to_comment("comment_123", "Reply")

        # Assert
        assert result["success"] is False
        assert "Network error" in result["error"]
        assert result["status_code"] is None
