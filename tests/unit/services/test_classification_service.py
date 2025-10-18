"""
Unit tests for CommentClassificationService.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.services.classification_service import CommentClassificationService


@pytest.mark.unit
@pytest.mark.service
class TestCommentClassificationService:
    """Test CommentClassificationService methods."""

    @patch("core.services.classification_service.Runner")
    async def test_classify_comment_success(self, mock_runner):
        """Test successful comment classification."""
        # Arrange
        mock_result = MagicMock()
        mock_result.final_output.classification = "question / inquiry"
        mock_result.final_output.confidence = 95
        mock_result.final_output.reasoning = "Contains question mark"
        mock_result.raw_responses = [MagicMock()]
        mock_result.raw_responses[0].usage.input_tokens = 100
        mock_result.raw_responses[0].usage.output_tokens = 50
        mock_runner.run = AsyncMock(return_value=mock_result)

        service = CommentClassificationService(api_key="test_key")

        # Act
        result = await service.classify_comment(
            comment_text="Сколько стоит доставка?",
            conversation_id="conv_123"
        )

        # Assert
        assert result.status == "success"
        assert result.classification == "question / inquiry"
        assert result.confidence == 95
        assert result.input_tokens == 100
        assert result.output_tokens == 50
        mock_runner.run.assert_called_once()

    @patch("core.services.classification_service.Runner")
    async def test_classify_comment_with_media_context(self, mock_runner):
        """Test classification with media context."""
        # Arrange
        mock_result = MagicMock()
        mock_result.final_output.classification = "positive"
        mock_result.final_output.confidence = 90
        mock_result.final_output.reasoning = "Positive feedback"
        mock_result.raw_responses = []
        mock_runner.run = AsyncMock(return_value=mock_result)

        service = CommentClassificationService(api_key="test_key")
        media_context = {
            "caption": "New product launch!",
            "media_type": "IMAGE",
            "username": "test_user"
        }

        # Act
        result = await service.classify_comment(
            comment_text="Отличный товар!",
            media_context=media_context
        )

        # Assert
        assert result.status == "success"
        assert result.classification == "positive"
        mock_runner.run.assert_called_once()

    @patch("core.services.classification_service.Runner")
    async def test_classify_comment_error_handling(self, mock_runner):
        """Test error handling when API fails."""
        # Arrange
        mock_runner.run = AsyncMock(side_effect=Exception("API Error"))
        service = CommentClassificationService(api_key="test_key")

        # Act
        result = await service.classify_comment(comment_text="Test comment")

        # Assert
        assert result.status == "error"
        assert result.classification == "spam / irrelevant"  # Fallback
        assert result.confidence == 0

    def test_generate_conversation_id_top_level(self):
        """Test conversation ID generation for top-level comment."""
        # Arrange
        service = CommentClassificationService(api_key="test_key")

        # Act
        conv_id = service.generate_conversation_id("comment_123")

        # Assert
        assert conv_id == "first_question_comment_comment_123"

    def test_generate_conversation_id_reply(self):
        """Test conversation ID generation for reply comment."""
        # Arrange
        service = CommentClassificationService(api_key="test_key")

        # Act
        conv_id = service.generate_conversation_id("comment_456", parent_id="comment_123")

        # Assert
        assert conv_id == "first_question_comment_comment_123"

    def test_create_media_description_simple(self):
        """Test media description formatting."""
        # Arrange
        service = CommentClassificationService(api_key="test_key")
        media_context = {
            "media_type": "IMAGE",
            "username": "test_user",
            "caption": "Test caption"
        }

        # Act
        description = service._create_media_description(media_context)

        # Assert
        assert "IMAGE" in description
        assert "@test_user" in description
        assert "Test caption" in description

    def test_create_media_description_carousel(self):
        """Test media description for carousel posts."""
        # Arrange
        service = CommentClassificationService(api_key="test_key")
        media_context = {
            "media_type": "CAROUSEL_ALBUM",
            "children_media_urls": ["url1", "url2", "url3"],
            "username": "test_user"
        }

        # Act
        description = service._create_media_description(media_context)

        # Assert
        assert "CAROUSEL_ALBUM" in description
        assert "3 изображений" in description
        assert "@test_user" in description
