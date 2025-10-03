"""
Unit tests for Pydantic schemas.

Tests cover validation, serialization, edge cases, and error handling
for all Pydantic v2 schemas in the application.
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from core.schemas.classification import (
    ClassificationRequest,
    ClassificationResponse,
    ClassificationResultData
)
from core.schemas.answer import (
    AnswerRequest,
    AnswerResponse,
    AnswerResultData
)
from core.schemas.webhook import (
    WebhookProcessingResponse,
    TestCommentResponse
)


# ============================================================================
# CLASSIFICATION SCHEMA TESTS
# ============================================================================

class TestClassificationRequest:
    """Tests for ClassificationRequest schema."""

    def test_valid_request(self):
        """Test creating valid classification request."""
        request = ClassificationRequest(
            comment_id="comment_123",
            comment_text="Какая цена?",
            username="test_user",
            media_id="media_123"
        )
        assert request.comment_id == "comment_123"
        assert request.comment_text == "Какая цена?"
        assert request.username == "test_user"
        assert request.media_id == "media_123"

    def test_minimal_request(self):
        """Test request with only required fields."""
        request = ClassificationRequest(
            comment_id="comment_123",
            comment_text="Test comment"
        )
        assert request.comment_id == "comment_123"
        assert request.username is None
        assert request.media_id is None

    def test_empty_comment_text_fails(self):
        """Test that empty comment text is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ClassificationRequest(
                comment_id="comment_123",
                comment_text=""  # Empty string should fail min_length=1
            )
        errors = exc_info.value.errors()
        assert any('comment_text' in str(err['loc']) for err in errors)

    def test_missing_required_fields(self):
        """Test that missing required fields raise validation error."""
        with pytest.raises(ValidationError):
            ClassificationRequest()  # Missing all required fields


class TestClassificationResponse:
    """Tests for ClassificationResponse schema."""

    def test_successful_response(self):
        """Test creating successful classification response."""
        now = datetime.utcnow()
        response = ClassificationResponse(
            status="success",
            comment_id="comment_123",
            classification="question / inquiry",
            confidence=95,
            reasoning="User is asking about pricing",
            input_tokens=50,
            output_tokens=30,
            processing_started_at=now,
            processing_completed_at=now
        )
        assert response.status == "success"
        assert response.classification == "question / inquiry"
        assert response.confidence == 95
        assert response.error is None

    def test_error_response(self):
        """Test error response."""
        response = ClassificationResponse(
            status="error",
            comment_id="comment_123",
            error="Classification service unavailable"
        )
        assert response.status == "error"
        assert response.classification is None
        assert response.error == "Classification service unavailable"

    def test_confidence_bounds(self):
        """Test confidence score validation (0-100)."""
        # Valid confidence
        response = ClassificationResponse(
            status="success",
            comment_id="test",
            confidence=0
        )
        assert response.confidence == 0

        response = ClassificationResponse(
            status="success",
            comment_id="test",
            confidence=100
        )
        assert response.confidence == 100

        # Invalid confidence (> 100)
        with pytest.raises(ValidationError):
            ClassificationResponse(
                status="success",
                comment_id="test",
                confidence=101
            )

        # Invalid confidence (< 0)
        with pytest.raises(ValidationError):
            ClassificationResponse(
                status="success",
                comment_id="test",
                confidence=-1
            )


# ============================================================================
# ANSWER SCHEMA TESTS
# ============================================================================

class TestAnswerRequest:
    """Tests for AnswerRequest schema."""

    def test_valid_request(self):
        """Test creating valid answer request."""
        request = AnswerRequest(
            comment_id="comment_123",
            comment_text="Сколько стоит?",
            username="user_456",
            media_id="media_789"
        )
        assert request.comment_id == "comment_123"
        assert request.comment_text == "Сколько стоит?"

    def test_empty_text_fails(self):
        """Test empty comment text validation."""
        with pytest.raises(ValidationError):
            AnswerRequest(
                comment_id="comment_123",
                comment_text=""
            )


class TestAnswerResponse:
    """Tests for AnswerResponse schema."""

    def test_successful_response_with_reply(self):
        """Test successful answer with Instagram reply."""
        response = AnswerResponse(
            status="success",
            comment_id="comment_123",
            answer="Цена начинается от 50,000₽",
            answer_confidence=0.95,
            answer_quality_score=85,
            input_tokens=100,
            output_tokens=50,
            processing_time_ms=1500,
            reply_sent=True,
            reply_id="reply_456"
        )
        assert response.status == "success"
        assert response.answer == "Цена начинается от 50,000₽"
        assert response.reply_sent is True
        assert response.reply_id == "reply_456"

    def test_confidence_validation(self):
        """Test answer confidence validation (0.0-1.0)."""
        # Valid
        response = AnswerResponse(
            status="success",
            comment_id="test",
            answer_confidence=0.5
        )
        assert response.answer_confidence == 0.5

        # Invalid (> 1.0)
        with pytest.raises(ValidationError):
            AnswerResponse(
                status="success",
                comment_id="test",
                answer_confidence=1.1
            )

    def test_quality_score_validation(self):
        """Test quality score validation (0-100)."""
        # Valid boundaries
        AnswerResponse(status="success", comment_id="test", answer_quality_score=0)
        AnswerResponse(status="success", comment_id="test", answer_quality_score=100)

        # Invalid
        with pytest.raises(ValidationError):
            AnswerResponse(status="success", comment_id="test", answer_quality_score=101)


# ============================================================================
# WEBHOOK SCHEMA TESTS
# ============================================================================

class TestWebhookProcessingResponse:
    """Tests for WebhookProcessingResponse schema."""

    def test_success_response(self):
        """Test successful webhook processing response."""
        response = WebhookProcessingResponse(
            status="success",
            message="Processed 3 comments",
            comment_id="comment_123",
            classification="question / inquiry",
            task_id="task_456"
        )
        assert response.status == "success"
        assert "3 comments" in response.message
        assert response.task_id == "task_456"

    def test_error_response(self):
        """Test error webhook response."""
        response = WebhookProcessingResponse(
            status="error",
            message="Invalid webhook signature"
        )
        assert response.status == "error"
        assert response.comment_id is None


class TestTestCommentResponse:
    """Tests for TestCommentResponse schema."""

    def test_full_response(self):
        """Test complete test comment response."""
        response = TestCommentResponse(
            status="success",
            message="Comment processed successfully",
            comment_id="test_123",
            classification="question / inquiry",
            answer="Test answer",
            processing_details={"duration_ms": 1200, "tokens": 150}
        )
        assert response.status == "success"
        assert response.answer == "Test answer"
        assert response.processing_details["duration_ms"] == 1200

    def test_minimal_response(self):
        """Test minimal response with only required fields."""
        response = TestCommentResponse(
            status="success",
            message="Processed"
        )
        assert response.status == "success"
        assert response.comment_id is None
        assert response.processing_details is None


# ============================================================================
# SERIALIZATION TESTS
# ============================================================================

class TestSchemaSerialization:
    """Test schema serialization/deserialization."""

    def test_classification_response_to_dict(self):
        """Test ClassificationResponse serialization."""
        response = ClassificationResponse(
            status="success",
            comment_id="comment_123",
            classification="positive feedback",
            confidence=98
        )
        data = response.model_dump()

        assert data["status"] == "success"
        assert data["comment_id"] == "comment_123"
        assert data["confidence"] == 98

    def test_answer_response_json_serialization(self):
        """Test AnswerResponse JSON serialization."""
        response = AnswerResponse(
            status="success",
            comment_id="comment_123",
            answer="Test answer",
            processing_time_ms=1000
        )
        json_str = response.model_dump_json()

        assert "success" in json_str
        assert "Test answer" in json_str

    def test_from_attributes_mode(self):
        """Test model_config from_attributes=True."""
        # This allows creating from ORM objects
        from types import SimpleNamespace

        mock_orm = SimpleNamespace(
            status="success",
            comment_id="test_123",
            classification="spam / irrelevant",
            confidence=75
        )

        response = ClassificationResponse.model_validate(mock_orm)
        assert response.comment_id == "test_123"
        assert response.confidence == 75
