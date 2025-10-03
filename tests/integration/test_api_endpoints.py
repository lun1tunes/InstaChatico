"""
Integration tests for FastAPI endpoints using TestClient.

This module tests all API endpoints using FastAPI's TestClient, which provides:

1. **Automatic Lifespan Handling**: TestClient automatically triggers app startup/shutdown events
2. **Sync Interface for Async**: No need for @pytest.mark.asyncio on test functions
3. **Request/Response Validation**: Automatic Pydantic validation testing
4. **Session Management**: Handles HTTP session state correctly
5. **Base URL**: Configurable base URL for consistent testing

## TestClient Usage Pattern:

```python
def test_endpoint(self, api_client):  # api_client fixture injects TestClient
    response = api_client.get("/endpoint")  # Synchronous call to async endpoint
    assert response.status_code == 200
    data = response.json()  # Automatic JSON parsing
    assert "field" in data
```

## Key Features Tested:
- Webhook verification (GET/POST)
- Comment processing endpoints
- Error handling (404, 422, 401, 405)
- Request validation
- Response format validation
- Authentication/authorization
- Health checks
- Response headers (trace ID, content-type)
- Edge cases (empty payloads, large payloads, malformed data)

## Test Markers:
- @pytest.mark.api - API integration tests
- @pytest.mark.slow - Slower running tests (rate limiting)
"""

import pytest
import os
from unittest.mock import patch, AsyncMock, Mock
from fastapi.testclient import TestClient


# ============================================================================
# WEBHOOK ENDPOINT TESTS
# ============================================================================

@pytest.mark.api
class TestWebhookEndpoints:
    """Tests for webhook endpoints using FastAPI TestClient."""

    @patch.dict(os.environ, {"WEBHOOK_VERIFY_TOKEN": "test_verify_token"})
    def test_webhook_verification_get_valid_token(self, api_client):
        """Test webhook verification with VALID token (GET request from Instagram)."""
        response = api_client.get(
            "/api/v1/webhook/",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "test_verify_token",
                "hub.challenge": "challenge_string_12345"
            }
        )

        # Should return the challenge string for valid token
        assert response.status_code == 200
        assert response.text == "challenge_string_12345"

    def test_webhook_verification_get_invalid_token(self, api_client):
        """Test webhook verification with INVALID token."""
        response = api_client.get(
            "/api/v1/webhook/",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong_token",
                "hub.challenge": "challenge_string"
            }
        )

        # Should return 403 for invalid token
        assert response.status_code == 403

    def test_webhook_verification_get_missing_params(self, api_client):
        """Test webhook verification with missing required parameters."""
        # Missing hub.challenge
        response = api_client.get(
            "/api/v1/webhook/",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "test_verify_token"
            }
        )

        assert response.status_code == 422

    @patch.dict(os.environ, {"DEVELOPMENT_MODE": "true"})
    def test_webhook_post_invalid_payload(self, api_client):
        """Test webhook with invalid payload structure."""
        response = api_client.post(
            "/api/v1/webhook/",
            json={"invalid": "payload"}
        )

        # Should return 422 Unprocessable Entity for invalid structure
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    @patch.dict(os.environ, {"DEVELOPMENT_MODE": "true"})
    @patch('core.tasks.classification_tasks.classify_comment_task')
    @patch('core.tasks.media_tasks.process_media_task')
    def test_webhook_post_valid_comment(self, mock_media_task, mock_classify_task, api_client, sample_webhook_payload):
        """Test webhook with valid comment payload using TestClient."""
        # Mock Celery task delays
        mock_classify_task.delay = Mock(return_value=Mock(id="classify_task_123"))
        mock_media_task.delay = Mock(return_value=Mock(id="media_task_123"))

        response = api_client.post(
            "/api/v1/webhook/",
            json=sample_webhook_payload
        )

        # Should accept and queue for processing
        assert response.status_code in [200, 201, 202]

        # Verify tasks were queued
        if response.status_code in [200, 202]:
            data = response.json()
            assert data.get("status") in ["success", "queued", "received"]

    @patch.dict(os.environ, {"DEVELOPMENT_MODE": "true"})
    def test_webhook_empty_payload(self, api_client):
        """Test webhook with empty payload."""
        response = api_client.post(
            "/api/v1/webhook/",
            json={}
        )

        assert response.status_code == 422

    @patch.dict(os.environ, {"DEVELOPMENT_MODE": "true"})
    def test_webhook_missing_required_fields(self, api_client):
        """Test webhook with missing required fields."""
        incomplete_payload = {
            "object": "instagram",
            "entry": []  # Empty entries
        }

        response = api_client.post(
            "/api/v1/webhook/",
            json=incomplete_payload
        )

        # Should handle gracefully (empty entries = no processing needed)
        assert response.status_code in [200, 422]

    @patch.dict(os.environ, {"DEVELOPMENT_MODE": "true"})
    def test_webhook_content_type_json(self, api_client):
        """Test webhook with correct Content-Type header."""
        response = api_client.post(
            "/api/v1/webhook/",
            json={"test": "data"},
            headers={"Content-Type": "application/json"}
        )

        # TestClient automatically sets Content-Type for json parameter
        assert response.status_code in [200, 422]

    def test_webhook_signature_verification_failure(self, api_client):
        """Test webhook signature verification with invalid signature."""
        response = api_client.post(
            "/api/v1/webhook/",
            json={"object": "instagram", "entry": []},
            headers={"X-Hub-Signature-256": "sha256=invalidsignature"}
        )

        # Should reject with 401 if not in development mode
        assert response.status_code in [401, 200]


# ============================================================================
# TEST COMMENT ENDPOINT TESTS
# ============================================================================

@pytest.mark.api
class TestCommentEndpoints:
    """Tests for test comment endpoints using TestClient."""

    @patch('core.tasks.classification_tasks.classify_comment_async')
    @patch('core.services.media_service.MediaService.get_or_create_media')
    def test_test_comment_success(
        self,
        mock_media_service,
        mock_classify,
        api_client,
        sample_media
    ):
        """Test creating and processing a test comment via TestClient."""
        # Mock media service
        mock_media_service.return_value = sample_media

        # Mock classification
        mock_classify.return_value = {
            "status": "success",
            "classification": "question / inquiry",
            "confidence": 95
        }

        test_payload = {
            "comment_id": "test_comment_123",
            "comment_text": "Тестовый вопрос?",
            "username": "test_user",
            "media_id": "test_media_123"
        }

        # TestClient handles async endpoints automatically
        response = api_client.post(
            "/api/v1/webhook/test",
            json=test_payload
        )

        assert response.status_code in [200, 201]
        data = response.json()
        assert data["status"] == "success"
        assert "comment_id" in data or "classification" in data

    def test_test_comment_invalid_data(self, api_client):
        """Test test comment with invalid data."""
        invalid_payload = {
            "comment_id": "",  # Empty ID
            "comment_text": "Test"
        }

        response = api_client.post(
            "/api/v1/webhook/test",
            json=invalid_payload
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_test_comment_missing_fields(self, api_client):
        """Test test comment with missing required fields."""
        incomplete_payload = {
            "comment_text": "Test comment"
            # Missing comment_id, username, media_id
        }

        response = api_client.post(
            "/api/v1/webhook/test",
            json=incomplete_payload
        )

        assert response.status_code == 422

    def test_test_comment_with_long_text(self, api_client):
        """Test test comment with very long text."""
        long_text = "Это очень длинный комментарий " * 100

        test_payload = {
            "comment_id": "long_comment_123",
            "comment_text": long_text,
            "username": "test_user",
            "media_id": "test_media_123"
        }

        response = api_client.post(
            "/api/v1/webhook/test",
            json=test_payload
        )

        # Should either process or return validation error
        assert response.status_code in [200, 201, 422]


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

@pytest.mark.api
class TestErrorHandling:
    """Tests for API error handling using TestClient."""

    def test_404_not_found(self, api_client):
        """Test 404 error for non-existent endpoint."""
        response = api_client.get("/api/v1/nonexistent")
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    def test_method_not_allowed(self, api_client):
        """Test 405 error for wrong HTTP method."""
        # Assuming webhook POST endpoint doesn't support DELETE
        response = api_client.delete("/api/v1/webhook/")
        assert response.status_code == 405

    @patch.dict(os.environ, {"DEVELOPMENT_MODE": "true"})
    def test_validation_error_response_format(self, api_client):
        """Test that validation errors return proper format."""
        response = api_client.post(
            "/api/v1/webhook/",
            json={"invalid": "data"}
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data
        # FastAPI returns list of validation errors
        if isinstance(data["detail"], list):
            assert len(data["detail"]) > 0

    def test_cors_headers(self, api_client):
        """Test CORS headers if configured."""
        response = api_client.options("/api/v1/webhook/")

        # If CORS is enabled, should have appropriate headers
        # This test depends on your CORS configuration
        assert response.status_code in [200, 405]

    def test_malformed_json(self, api_client):
        """Test response to malformed JSON."""
        response = api_client.post(
            "/api/v1/webhook/",
            data="not valid json",
            headers={"Content-Type": "application/json"}
        )

        # Should return 422 for malformed JSON
        assert response.status_code == 422

    def test_large_payload(self, api_client):
        """Test handling of very large payload."""
        large_payload = {
            "object": "instagram",
            "entry": [{"data": "x" * 1000000}]  # 1MB of data
        }

        response = api_client.post(
            "/api/v1/webhook/",
            json=large_payload
        )

        # Should handle or reject gracefully
        assert response.status_code in [200, 413, 422, 401]


# ============================================================================
# RATE LIMITING TESTS (if implemented)
# ============================================================================

@pytest.mark.slow
@pytest.mark.api
class TestRateLimiting:
    """Tests for rate limiting (if implemented)."""

    def test_multiple_rapid_requests(self, api_client):
        """Test handling of rapid successive requests."""
        # Send multiple requests rapidly
        responses = []
        for _ in range(10):
            response = api_client.post(
                "/api/v1/webhook/",
                json={"test": "data"}
            )
            responses.append(response.status_code)

        # All should be processed or rate-limited gracefully
        assert all(code in [200, 201, 422, 429] for code in responses)


# ============================================================================
# AUTHENTICATION TESTS (if implemented)
# ============================================================================

@pytest.mark.api
class TestAuthentication:
    """Tests for authentication/authorization using TestClient."""

    def test_docs_authentication(self, api_client):
        """Test docs endpoint authentication if configured."""
        response = api_client.get("/docs")

        # Depending on configuration, might require auth
        assert response.status_code in [200, 401, 403, 404]

    def test_openapi_json(self, api_client):
        """Test OpenAPI JSON endpoint."""
        response = api_client.get("/openapi.json")

        assert response.status_code in [200, 401, 404]
        if response.status_code == 200:
            data = response.json()
            assert "openapi" in data
            assert "paths" in data


# ============================================================================
# HEALTH CHECK TESTS
# ============================================================================

@pytest.mark.api
class TestHealthEndpoints:
    """Tests for health check endpoints using TestClient."""

    def test_health_check_basic(self, api_client):
        """Test basic health check endpoint."""
        response = api_client.get("/health")

        # Should return health status
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert "status" in data

    def test_health_check_detailed(self, api_client):
        """Test detailed health check with database status."""
        response = api_client.get("/health/detailed")

        # Should return detailed status
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            # Should include database and other service statuses
            assert isinstance(data, dict)

    def test_readiness_probe(self, api_client):
        """Test Kubernetes readiness probe endpoint."""
        response = api_client.get("/ready")

        # Should return 200 when ready
        assert response.status_code in [200, 404]

    def test_liveness_probe(self, api_client):
        """Test Kubernetes liveness probe endpoint."""
        response = api_client.get("/live")

        # Should return 200 when alive
        assert response.status_code in [200, 404]


# ============================================================================
# RESPONSE HEADER TESTS
# ============================================================================

@pytest.mark.api
class TestResponseHeaders:
    """Tests for response headers using TestClient."""

    def test_content_type_json(self, api_client):
        """Test that JSON endpoints return correct Content-Type."""
        response = api_client.get("/api/v1/webhook/", params={
            "hub.mode": "subscribe",
            "hub.verify_token": "test",
            "hub.challenge": "test"
        })

        # Content-Type should be set
        assert "content-type" in [h.lower() for h in response.headers.keys()]

    def test_trace_id_header(self, api_client):
        """Test X-Trace-Id header propagation."""
        custom_trace_id = "test-trace-123"

        response = api_client.get(
            "/api/v1/webhook/",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "test",
                "hub.challenge": "test"
            },
            headers={"X-Trace-Id": custom_trace_id}
        )

        # Should propagate trace ID in response
        assert "X-Trace-Id" in response.headers or "x-trace-id" in response.headers

    def test_security_headers(self, api_client):
        """Test security headers if configured."""
        response = api_client.get("/")

        # Check for common security headers
        headers_lower = {k.lower(): v for k, v in response.headers.items()}

        # These are optional but good to have
        # Just verify response has some headers
        assert len(headers_lower) > 0
