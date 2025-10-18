"""
Unit tests for InstagramGraphAPIService.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from core.services.instagram_service import InstagramGraphAPIService


@pytest.mark.unit
@pytest.mark.service
class TestInstagramGraphAPIService:
    """Test InstagramGraphAPIService methods."""

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_send_reply_success(self, mock_session_class):
        """Test successful Instagram reply."""
        # Arrange
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"id": "reply_123"})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_session_class.return_value = mock_session

        service = InstagramGraphAPIService(access_token="test_token")

        # Act
        result = await service.send_reply_to_comment("comment_123", "Test reply")

        # Assert
        assert result["success"] is True
        assert result["reply_id"] == "reply_123"
        assert result["status_code"] == 200
        mock_session.post.assert_called_once()

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_send_reply_failure(self, mock_session_class):
        """Test failed Instagram reply."""
        # Arrange
        mock_response = AsyncMock()
        mock_response.status = 400
        mock_response.json = AsyncMock(return_value={"error": {"message": "Bad request"}})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_session_class.return_value = mock_session

        service = InstagramGraphAPIService(access_token="test_token")

        # Act
        result = await service.send_reply_to_comment("comment_123", "Test reply")

        # Assert
        assert result["success"] is False
        assert result["status_code"] == 400

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_send_reply_rate_limit(self, mock_session_class):
        """Test rate limit handling."""
        # Arrange
        mock_response = AsyncMock()
        mock_response.status = 429
        mock_response.json = AsyncMock(return_value={
            "error": {"code": 2, "message": "Please retry"}
        })
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_session_class.return_value = mock_session

        service = InstagramGraphAPIService(access_token="test_token")

        # Act
        result = await service.send_reply_to_comment("comment_123", "Test reply")

        # Assert
        assert result["success"] is False
        assert result["status_code"] == 429

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_hide_comment_success(self, mock_session_class):
        """Test successful comment hiding."""
        # Arrange
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"success": True})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_session_class.return_value = mock_session

        service = InstagramGraphAPIService(access_token="test_token")

        # Act
        result = await service.hide_comment("comment_123", hide=True)

        # Assert
        assert result["success"] is True
        assert result["status_code"] == 200

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_unhide_comment(self, mock_session_class):
        """Test successful comment unhiding."""
        # Arrange
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"success": True})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_session_class.return_value = mock_session

        service = InstagramGraphAPIService(access_token="test_token")

        # Act
        result = await service.hide_comment("comment_123", hide=False)

        # Assert
        assert result["success"] is True
        assert result["status_code"] == 200

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_hide_comment_exception(self, mock_session_class):
        """Test exception handling path when hiding comment fails early."""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(side_effect=Exception("timeout talking to API"))
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_class.return_value = mock_session

        service = InstagramGraphAPIService(access_token="test_token")

        result = await service.hide_comment("comment_999", hide=True)

        assert result["success"] is False
        assert "timeout talking to API" in result["error"]
        assert result["status_code"] is None

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_hide_comment_http_error(self, mock_session_class):
        """Handle non-200 responses when hiding comments."""
        mock_response = AsyncMock()
        mock_response.status = 400
        mock_response.json = AsyncMock(return_value={"error": {"message": "bad"}})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_class.return_value = mock_session

        service = InstagramGraphAPIService(access_token="test_token")

        result = await service.hide_comment("comment_123", hide=True)

        assert result["success"] is False
        assert result["error"] == {"error": {"message": "bad"}}
        assert result["status_code"] == 400

    @patch("core.services.instagram_service.settings")
    def test_service_requires_token(self, mock_settings):
        """Test that service raises error when no token provided."""
        # Arrange
        mock_settings.instagram.access_token = None

        # Act & Assert
        with pytest.raises(ValueError, match="Instagram access token is required"):
            InstagramGraphAPIService(access_token=None)

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_exception_handling(self, mock_session_class):
        """Test exception handling in send_reply."""
        # Arrange
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(side_effect=Exception("Network error"))
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_session_class.return_value = mock_session

        service = InstagramGraphAPIService(access_token="test_token")

        # Act
        result = await service.send_reply_to_comment("comment_123", "Test reply")

        # Assert
        assert result["success"] is False
        assert "Network error" in result["error"]
        assert result["status_code"] is None

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_get_media_info_success(self, mock_session_class):
        """Test successful media info retrieval."""
        # Arrange
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "id": "media_123",
            "media_type": "IMAGE",
            "caption": "Test caption"
        })
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_session_class.return_value = mock_session

        service = InstagramGraphAPIService(access_token="test_token")

        # Act
        result = await service.get_media_info("media_123")

        # Assert
        assert result["success"] is True
        assert result["media_info"]["id"] == "media_123"
        assert result["status_code"] == 200

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_get_media_info_carousel_children(self, mock_session_class):
        """Test media info retrieval with carousel children data."""
        carousel_payload = {
            "id": "media_carousel",
            "media_type": "CAROUSEL_ALBUM",
            "children": {
                "data": [
                    {"id": "child_1", "media_url": "https://cdn/img1.jpg", "media_type": "IMAGE"},
                    {"id": "child_2", "media_url": "https://cdn/img2.jpg", "media_type": "IMAGE"},
                ]
            },
        }
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=carousel_payload)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_class.return_value = mock_session

        service = InstagramGraphAPIService(access_token="test_token")

        result = await service.get_media_info("media_carousel")

        assert result["success"] is True
        assert result["media_info"]["media_type"] == "CAROUSEL_ALBUM"
        children = result["media_info"]["children"]["data"]
        assert len(children) == 2
        assert {child["id"] for child in children} == {"child_1", "child_2"}
        # Ensure we requested carousel children fields from API
        _, kwargs = mock_session.get.call_args
        fields_param = kwargs["params"]["fields"]
        assert "children{media_url,media_type}" in fields_param

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_get_media_info_failure(self, mock_session_class):
        mock_response = AsyncMock()
        mock_response.status = 404
        mock_response.json = AsyncMock(return_value={"error": "not found"})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_session_class.return_value = mock_session

        service = InstagramGraphAPIService(access_token="test_token")
        result = await service.get_media_info("media_404")

        assert result["success"] is False
        assert result["status_code"] == 404

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_get_media_info_exception(self, mock_session_class):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(side_effect=Exception("network"))
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_class.return_value = mock_session

        service = InstagramGraphAPIService(access_token="test_token")
        result = await service.get_media_info("media")

        assert result["success"] is False
        assert result["status_code"] is None

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_get_comment_info_success(self, mock_session_class):
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"id": "comment_1"})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_class.return_value = mock_session

        service = InstagramGraphAPIService(access_token="test_token")
        result = await service.get_comment_info("comment_1")

        assert result["success"] is True
        assert result["comment_info"]["id"] == "comment_1"

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_get_comment_info_failure(self, mock_session_class):
        mock_response = AsyncMock()
        mock_response.status = 404
        mock_response.json = AsyncMock(return_value={"error": "missing"})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_class.return_value = mock_session

        service = InstagramGraphAPIService(access_token="test_token")
        result = await service.get_comment_info("comment_missing")

        assert result["success"] is False
        assert result["status_code"] == 404

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_get_comment_info_exception(self, mock_session_class):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(side_effect=Exception("boom"))
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_class.return_value = mock_session

        service = InstagramGraphAPIService(access_token="test_token")
        result = await service.get_comment_info("comment_error")

        assert result["success"] is False
        assert result["status_code"] is None
        assert "boom" in result["error"]

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_validate_token_success(self, mock_session_class):
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"data": {"is_valid": True}})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_class.return_value = mock_session

        service = InstagramGraphAPIService(access_token="test_token")
        result = await service.validate_token()

        assert result["success"] is True

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_validate_token_failure(self, mock_session_class):
        mock_response = AsyncMock()
        mock_response.status = 401
        mock_response.json = AsyncMock(return_value={"error": "invalid"})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_class.return_value = mock_session

        service = InstagramGraphAPIService(access_token="test_token")
        result = await service.validate_token()

        assert result["success"] is False
        assert result["status_code"] == 401

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_validate_token_exception(self, mock_session_class):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(side_effect=Exception("kaboom"))
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_class.return_value = mock_session

        service = InstagramGraphAPIService(access_token="test_token")
        result = await service.validate_token()

        assert result["success"] is False
        assert result["status_code"] is None
        assert "kaboom" in result["error"]

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_get_page_info_success(self, mock_session_class):
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"id": "page_1"})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_class.return_value = mock_session

        service = InstagramGraphAPIService(access_token="test_token")
        result = await service.get_page_info()

        assert result["success"] is True
        assert result["page_info"]["id"] == "page_1"

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_get_page_info_failure(self, mock_session_class):
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.json = AsyncMock(return_value={"error": "server"})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_class.return_value = mock_session

        service = InstagramGraphAPIService(access_token="test_token")
        result = await service.get_page_info()

        assert result["success"] is False
        assert result["status_code"] == 500

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_get_page_info_exception(self, mock_session_class):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(side_effect=Exception("boom"))
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_class.return_value = mock_session

        service = InstagramGraphAPIService(access_token="test_token")
        result = await service.get_page_info()

        assert result["success"] is False
        assert result["status_code"] is None
