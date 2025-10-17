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

    @patch("core.services.answer_service.Runner")
    async def test_generate_answer_success(self, mock_runner):
        """Test successful answer generation."""
        # Arrange
        mock_result = MagicMock()
        mock_result.final_output = "Доставка стоит 300 рублей"
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
        assert result.processing_time_ms > 0

    @patch("core.services.answer_service.Runner")
    async def test_generate_answer_with_username_attribution(self, mock_runner):
        """Test that username is added to question text."""
        # Arrange
        mock_result = MagicMock()
        mock_result.final_output = "Answer"
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
        mock_result.final_output = "Answer"
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
