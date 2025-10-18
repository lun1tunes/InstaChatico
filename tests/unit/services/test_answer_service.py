"""
Unit tests for QuestionAnswerService.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.services.answer_service import QuestionAnswerService


@pytest.mark.unit
@pytest.mark.service
class TestQuestionAnswerService:
    """Test QuestionAnswerService methods."""

    @patch("core.services.answer_service.time.time")
    @patch("core.services.answer_service.Runner")
    async def test_generate_answer_success(self, mock_runner, mock_time):
        """Test successful answer generation."""
        # Arrange
        # Mock time to simulate 100ms processing time
        mock_time.side_effect = [1000.0, 1000.1]  # Start and end times

        mock_result = MagicMock()
        mock_result.final_output.answer = "Доставка стоит 300 рублей"
        mock_result.final_output.confidence = 0.95
        mock_result.final_output.quality_score = 85
        mock_result.raw_responses = [MagicMock()]
        mock_result.raw_responses[0].usage.input_tokens = 200
        mock_result.raw_responses[0].usage.output_tokens = 150
        mock_runner.run = AsyncMock(return_value=mock_result)

        service = QuestionAnswerService(api_key="test_key")

        # Act
        result = await service.generate_answer(
            question_text="Сколько стоит доставка?",
            username="test_user"
        )

        # Assert
        assert result.status == "success"
        assert result.answer == "Доставка стоит 300 рублей"
        assert result.input_tokens == 200
        assert result.output_tokens == 150
        assert result.processing_time_ms == 100  # 1000.1 - 1000.0 = 0.1s = 100ms

    @patch("core.services.answer_service.Runner")
    async def test_generate_answer_with_username_attribution(self, mock_runner):
        """Test that username is added to question text."""
        # Arrange
        mock_result = MagicMock()
        mock_result.final_output.answer = "Answer"
        mock_result.final_output.confidence = 0.80
        mock_result.final_output.quality_score = 70
        mock_result.raw_responses = []
        mock_runner.run = AsyncMock(return_value=mock_result)

        service = QuestionAnswerService(api_key="test_key")

        # Act
        await service.generate_answer(
            question_text="Test question",
            username="john_doe"
        )

        # Assert
        call_args = mock_runner.run.call_args
        input_text = call_args.kwargs.get("input") or call_args.args[1]
        assert "@john_doe:" in input_text

    @patch("core.services.answer_service.Runner")
    async def test_generate_answer_truncates_long_text(self, mock_runner):
        """Test that long questions are truncated to 1000 chars."""
        # Arrange
        mock_result = MagicMock()
        mock_result.final_output.answer = "Answer"
        mock_result.final_output.confidence = 0.80
        mock_result.final_output.quality_score = 70
        mock_result.raw_responses = []
        mock_runner.run = AsyncMock(return_value=mock_result)

        service = QuestionAnswerService(api_key="test_key")
        long_question = "a" * 1500

        # Act
        await service.generate_answer(question_text=long_question)

        # Assert
        call_args = mock_runner.run.call_args
        input_text = call_args.kwargs.get("input") or call_args.args[1]
        assert len(input_text) <= 1003  # 1000 + "..."

    @patch("core.services.answer_service.Runner")
    async def test_generate_answer_with_conversation_id(self, mock_runner):
        """Test answer generation with conversation_id uses session."""
        # Arrange
        mock_result = MagicMock()
        mock_result.final_output.answer = "Answer with session"
        mock_result.final_output.confidence = 0.90
        mock_result.final_output.quality_score = 80
        mock_result.raw_responses = []
        mock_runner.run = AsyncMock(return_value=mock_result)

        service = QuestionAnswerService(api_key="test_key")

        # Act
        result = await service.generate_answer(
            question_text="Test question",
            conversation_id="conv_123"
        )

        # Assert
        assert result.status == "success"
        assert result.comment_id == "conv_123"
        # Verify session was passed to Runner.run
        call_args = mock_runner.run.call_args
        assert "session" in call_args.kwargs

    @patch("core.services.answer_service.Runner")
    async def test_generate_answer_without_usage_data(self, mock_runner):
        """Test answer generation when raw_responses has no usage data."""
        # Arrange
        mock_result = MagicMock()
        mock_result.final_output.answer = "Answer"
        mock_result.final_output.confidence = 0.85
        mock_result.final_output.quality_score = 75
        # Mock raw_responses with no usage attribute
        mock_response = MagicMock()
        del mock_response.usage  # Remove usage attribute
        mock_result.raw_responses = [mock_response]
        mock_runner.run = AsyncMock(return_value=mock_result)

        service = QuestionAnswerService(api_key="test_key")

        # Act
        result = await service.generate_answer(question_text="Test question")

        # Assert
        assert result.status == "success"
        assert result.input_tokens is None
        assert result.output_tokens is None

    @patch("core.services.answer_service.Runner")
    async def test_generate_answer_error_handling(self, mock_runner):
        """Test error handling when answer generation fails."""
        # Arrange
        mock_runner.run = AsyncMock(side_effect=Exception("API Error"))
        service = QuestionAnswerService(api_key="test_key")

        # Act
        result = await service.generate_answer(question_text="Test question")

        # Assert
        assert result.status == "error"
        assert result.error == "API Error"
        assert result.answer is None
        assert result.answer_confidence == 0.0
        assert result.comment_id == "unknown"
