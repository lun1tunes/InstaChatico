"""
Unit tests for service layer.

Tests cover classification service, answer service, media service,
and media analysis service with mocked dependencies.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime

from core.services.classification_service import CommentClassificationService
from core.services.answer_service import QuestionAnswerService
from core.services.media_service import MediaService
from core.services.media_analysis_service import MediaAnalysisService
from core.schemas.classification import ClassificationResponse
from core.schemas.answer import AnswerResponse


# ============================================================================
# CLASSIFICATION SERVICE TESTS
# ============================================================================

class TestCommentClassificationService:
    """Tests for CommentClassificationService."""

    @pytest.mark.asyncio
    async def test_format_input_with_username(self):
        """Test username attribution in formatted input."""
        service = CommentClassificationService()

        formatted = service._format_input_with_context(
            comment_text="Какая цена?",
            username="test_user",
            conversation_id=None,
            media_context=None
        )

        assert "@test_user:" in formatted
        assert "Какая цена?" in formatted

    @pytest.mark.asyncio
    async def test_format_input_with_media_context(self):
        """Test media context inclusion in formatted input."""
        service = CommentClassificationService()

        media_context = {
            "caption": "Продажа квартиры",
            "media_type": "IMAGE",
            "media_context": "Описание: Современная квартира",
            "username": "business_account"
        }

        formatted = service._format_input_with_context(
            comment_text="Интересно!",
            username="user123",
            media_context=media_context
        )

        assert "Продажа квартиры" in formatted
        assert "IMAGE" in formatted
        assert "Современная квартира" in formatted
        assert "@user123:" in formatted

    @pytest.mark.asyncio
    async def test_format_input_without_username(self):
        """Test formatted input when username is None."""
        service = CommentClassificationService()

        formatted = service._format_input_with_context(
            comment_text="Test comment",
            username=None
        )

        # Should not have @ prefix when username is None
        assert formatted == "Test comment"

    @pytest.mark.asyncio
    async def test_sanitize_input(self):
        """Test input sanitization."""
        service = CommentClassificationService()

        # Test normal input
        sanitized = service._sanitize_input("Нормальный текст")
        assert sanitized == "Нормальный текст"

        # Test with special characters (should be preserved in our case)
        sanitized = service._sanitize_input("Test <script>alert('xss')</script>")
        assert "alert" in sanitized  # Basic sanitization, not HTML escaping

    def test_create_error_response(self):
        """Test error response creation."""
        service = CommentClassificationService()

        error_response = service._create_error_response("Network error")

        assert isinstance(error_response, ClassificationResponse)
        assert error_response.status == "error"
        assert error_response.classification == "spam / irrelevant"  # Safe fallback
        assert error_response.error == "Network error"
        assert error_response.confidence == 0

    @pytest.mark.asyncio
    @patch('core.services.classification_service.Runner')
    async def test_classify_comment_success(self, mock_runner):
        """Test successful comment classification."""
        # Mock the Runner.run response
        mock_result = Mock()
        mock_result.final_output = Mock(
            classification="question / inquiry",
            confidence=95,
            reasoning="User is asking about price"
        )
        mock_result.usage = Mock(input_tokens=50, output_tokens=30)
        mock_runner.run = AsyncMock(return_value=mock_result)

        service = CommentClassificationService()
        response = await service.classify_comment(
            comment_text="Какая цена?",
            username="test_user"
        )

        assert response.status == "success"
        assert response.classification == "question / inquiry"
        assert response.confidence == 95
        assert response.input_tokens == 50
        assert response.output_tokens == 30

    @pytest.mark.asyncio
    @patch('core.services.classification_service.Runner')
    async def test_classify_comment_with_session(self, mock_runner):
        """Test classification with conversation session."""
        mock_result = Mock()
        mock_result.final_output = Mock(
            classification="positive feedback",
            confidence=90,
            reasoning="Follow-up thank you"
        )
        mock_runner.run = AsyncMock(return_value=mock_result)

        service = CommentClassificationService()
        response = await service.classify_comment(
            comment_text="Спасибо!",
            conversation_id="conv_123",
            username="user456"
        )

        # Verify session was used
        mock_runner.run.assert_called_once()
        call_args = mock_runner.run.call_args
        assert 'session' in call_args.kwargs


# ============================================================================
# ANSWER SERVICE TESTS
# ============================================================================

class TestQuestionAnswerService:
    """Tests for QuestionAnswerService."""

    @pytest.mark.asyncio
    @patch('core.services.answer_service.Runner')
    async def test_generate_answer_success(self, mock_runner):
        """Test successful answer generation."""
        mock_result = Mock()
        mock_result.final_output = Mock(
            answer="Цена начинается от 50,000₽",
            confidence=0.92,
            quality_score=88,
            reasoning="Provided pricing information",
            is_helpful=True,
            contains_contact_info=False,
            tone="professional"
        )
        mock_result.usage = Mock(input_tokens=80, output_tokens=40)
        mock_runner.run = AsyncMock(return_value=mock_result)

        service = QuestionAnswerService()
        response = await service.generate_answer(
            question_text="Сколько стоит?",
            username="buyer123"
        )

        assert response.status == "success"
        assert "50,000₽" in response.answer
        assert response.answer_confidence == 0.92
        assert response.answer_quality_score == 88

    def test_create_error_response(self):
        """Test error response creation."""
        service = QuestionAnswerService()

        error_response = service._create_error_response("API timeout")

        assert isinstance(error_response, AnswerResponse)
        assert error_response.status == "error"
        assert error_response.answer is None
        assert error_response.error == "API timeout"
        assert error_response.answer_confidence == 0.0

    def test_estimate_tokens(self):
        """Test token estimation."""
        service = QuestionAnswerService()

        # Short text
        tokens = service._estimate_tokens("Hello world")
        assert tokens > 0
        assert tokens < 10

        # Longer text
        long_text = "This is a much longer text " * 20
        long_tokens = service._estimate_tokens(long_text)
        assert long_tokens > tokens


# ============================================================================
# MEDIA SERVICE TESTS
# ============================================================================

class TestMediaService:
    """Tests for MediaService."""

    @pytest.mark.asyncio
    async def test_parse_timestamp_valid(self):
        """Test valid timestamp parsing."""
        service = MediaService()

        # ISO format
        result = service._parse_timestamp("2025-10-03T10:00:00Z")
        assert isinstance(result, datetime)
        assert result.year == 2025
        assert result.month == 10
        assert result.day == 3

    @pytest.mark.asyncio
    async def test_parse_timestamp_invalid(self):
        """Test invalid timestamp handling."""
        service = MediaService()

        # Invalid format
        result = service._parse_timestamp("invalid-date")
        assert result is None

        # None input
        result = service._parse_timestamp(None)
        assert result is None

    def test_parse_owner_dict(self):
        """Test parsing owner from dict."""
        service = MediaService()

        result = service._parse_owner({"id": "owner_123"})
        assert result == "owner_123"

    def test_parse_owner_string(self):
        """Test parsing owner from string."""
        service = MediaService()

        result = service._parse_owner("owner_456")
        assert result == "owner_456"

    def test_parse_owner_none(self):
        """Test parsing None owner."""
        service = MediaService()

        result = service._parse_owner(None)
        assert result is None

    def test_parse_owner_invalid_type(self):
        """Test parsing invalid owner type."""
        service = MediaService()

        result = service._parse_owner(12345)  # Number instead of string/dict
        assert result is None


# ============================================================================
# MEDIA ANALYSIS SERVICE TESTS
# ============================================================================

class TestMediaAnalysisService:
    """Tests for MediaAnalysisService."""

    @pytest.mark.asyncio
    @patch('core.services.media_analysis_service._analyze_image_implementation')
    async def test_analyze_media_image_success(self, mock_analyze):
        """Test successful media image analysis."""
        mock_analyze.return_value = """
        Описание: Профессиональное фото квартиры
        Ключевые элементы: Большие окна, современная мебель
        Текст на изображении: Цена: 5,000,000₽
        """

        service = MediaAnalysisService()
        result = await service.analyze_media_image(
            media_url="https://example.com/image.jpg",
            caption="Продажа квартиры"
        )

        assert result is not None
        assert "квартиры" in result
        assert "5,000,000₽" in result
        mock_analyze.assert_called_once()

    @pytest.mark.asyncio
    @patch('core.services.media_analysis_service._analyze_image_implementation')
    async def test_analyze_media_image_error(self, mock_analyze):
        """Test error handling in image analysis."""
        mock_analyze.return_value = "Ошибка при анализе изображения: Invalid URL"

        service = MediaAnalysisService()
        result = await service.analyze_media_image(
            media_url="https://invalid-url.com/image.jpg"
        )

        assert result is None  # Error responses return None

    @pytest.mark.asyncio
    @patch('core.services.media_analysis_service._analyze_image_implementation')
    async def test_analyze_media_image_empty_result(self, mock_analyze):
        """Test handling of empty analysis result."""
        mock_analyze.return_value = None

        service = MediaAnalysisService()
        result = await service.analyze_media_image(
            media_url="https://example.com/image.jpg"
        )

        assert result is None

    @pytest.mark.asyncio
    @patch('core.services.media_analysis_service._analyze_image_implementation')
    async def test_analyze_with_caption_context(self, mock_analyze):
        """Test that caption is included in analysis context."""
        mock_analyze.return_value = "Analysis result"

        service = MediaAnalysisService()
        await service.analyze_media_image(
            media_url="https://example.com/image.jpg",
            caption="Специальное предложение!"
        )

        # Check that caption was included in the additional_context parameter
        call_args = mock_analyze.call_args
        additional_context = call_args.kwargs.get('additional_context', '')
        assert "Специальное предложение!" in additional_context
