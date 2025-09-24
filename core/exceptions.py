"""
Custom exceptions for InstaChatico application.
Provides structured error handling with proper HTTP status codes and logging.
"""

from typing import Optional, Dict, Any
from fastapi import HTTPException


class InstaChaticBaseException(Exception):
    """Base exception for InstaChatico application"""
    
    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.details = details or {}
        super().__init__(self.message)


class InstaChaticHTTPException(HTTPException):
    """HTTP exception with additional context"""
    
    def __init__(
        self,
        status_code: int,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        self.error_code = error_code
        self.details = details or {}
        detail = {
            "error": error_code or "HTTPException",
            "message": message,
            "details": self.details
        }
        super().__init__(status_code=status_code, detail=detail)


# Database Exceptions
class DatabaseError(InstaChaticBaseException):
    """Database operation error"""
    pass


class RecordNotFoundError(InstaChaticBaseException):
    """Record not found in database"""
    pass


class DuplicateRecordError(InstaChaticBaseException):
    """Duplicate record creation attempt"""
    pass


class DatabaseConnectionError(InstaChaticBaseException):
    """Database connection error"""
    pass


# Webhook Exceptions
class WebhookValidationError(InstaChaticBaseException):
    """Webhook payload validation error"""
    pass


class WebhookSignatureError(InstaChaticBaseException):
    """Webhook signature verification error"""
    pass


class WebhookProcessingError(InstaChaticBaseException):
    """Webhook processing error"""
    pass


# Classification Exceptions
class ClassificationError(InstaChaticBaseException):
    """Comment classification error"""
    pass


class ClassificationServiceError(InstaChaticBaseException):
    """Classification service error"""
    pass


class ClassificationTimeoutError(InstaChaticBaseException):
    """Classification timeout error"""
    pass


class InvalidClassificationError(InstaChaticBaseException):
    """Invalid classification result"""
    pass


# Answer Generation Exceptions
class AnswerGenerationError(InstaChaticBaseException):
    """Answer generation error"""
    pass


class AnswerServiceError(InstaChaticBaseException):
    """Answer service error"""
    pass


class AnswerTimeoutError(InstaChaticBaseException):
    """Answer generation timeout error"""
    pass


class InvalidAnswerError(InstaChaticBaseException):
    """Invalid answer result"""
    pass


# Instagram API Exceptions
class InstagramAPIError(InstaChaticBaseException):
    """Instagram API error"""
    
    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        api_error_code: Optional[str] = None,
        api_error_type: Optional[str] = None,
        fbtrace_id: Optional[str] = None,
        **kwargs
    ):
        self.status_code = status_code
        self.api_error_code = api_error_code
        self.api_error_type = api_error_type
        self.fbtrace_id = fbtrace_id
        
        details = {
            "status_code": status_code,
            "api_error_code": api_error_code,
            "api_error_type": api_error_type,
            "fbtrace_id": fbtrace_id,
            **kwargs
        }
        super().__init__(message, "InstagramAPIError", details)


class InstagramAuthenticationError(InstagramAPIError):
    """Instagram authentication/authorization error"""
    pass


class InstagramRateLimitError(InstagramAPIError):
    """Instagram API rate limit exceeded"""
    
    def __init__(
        self,
        message: str = "Instagram API rate limit exceeded",
        retry_after: Optional[int] = None,
        **kwargs
    ):
        self.retry_after = retry_after
        super().__init__(message, retry_after=retry_after, **kwargs)


class InstagramReplyError(InstagramAPIError):
    """Instagram reply sending error"""
    pass


class InstagramTokenValidationError(InstagramAPIError):
    """Instagram token validation error"""
    pass


# OpenAI/LLM Exceptions
class LLMError(InstaChaticBaseException):
    """LLM service error"""
    pass


class LLMTimeoutError(LLMError):
    """LLM request timeout"""
    pass


class LLMRateLimitError(LLMError):
    """LLM rate limit exceeded"""
    
    def __init__(
        self,
        message: str = "LLM API rate limit exceeded",
        retry_after: Optional[int] = None,
        **kwargs
    ):
        self.retry_after = retry_after
        super().__init__(message, "LLMRateLimitError", {"retry_after": retry_after, **kwargs})


class LLMAuthenticationError(LLMError):
    """LLM authentication error"""
    pass


class LLMInvalidResponseError(LLMError):
    """LLM returned invalid response"""
    pass


# Task/Processing Exceptions
class TaskError(InstaChaticBaseException):
    """Celery task error"""
    pass


class TaskTimeoutError(TaskError):
    """Task execution timeout"""
    pass


class TaskRetryError(TaskError):
    """Task retry limit exceeded"""
    
    def __init__(
        self,
        message: str,
        retry_count: int,
        max_retries: int,
        **kwargs
    ):
        self.retry_count = retry_count
        self.max_retries = max_retries
        super().__init__(
            message,
            "TaskRetryError",
            {"retry_count": retry_count, "max_retries": max_retries, **kwargs}
        )


class ProcessingError(InstaChaticBaseException):
    """General processing error"""
    pass


# Configuration Exceptions
class ConfigurationError(InstaChaticBaseException):
    """Configuration error"""
    pass


class MissingConfigurationError(ConfigurationError):
    """Required configuration missing"""
    pass


class InvalidConfigurationError(ConfigurationError):
    """Invalid configuration value"""
    pass


# Validation Exceptions
class ValidationError(InstaChaticBaseException):
    """Data validation error"""
    pass


class SchemaValidationError(ValidationError):
    """Pydantic schema validation error"""
    pass


# Service Exceptions
class ServiceError(InstaChaticBaseException):
    """Service layer error"""
    pass


class ServiceUnavailableError(ServiceError):
    """Service temporarily unavailable"""
    pass


class ExternalServiceError(ServiceError):
    """External service error"""
    pass


# Utility functions for exception handling
def create_http_exception(
    status_code: int,
    message: str,
    error_code: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
) -> InstaChaticHTTPException:
    """Create HTTP exception with structured error response"""
    return InstaChaticHTTPException(
        status_code=status_code,
        message=message,
        error_code=error_code,
        details=details
    )


def handle_database_error(error: Exception) -> InstaChaticBaseException:
    """Convert database errors to application exceptions"""
    error_message = str(error)
    
    if "not found" in error_message.lower():
        return RecordNotFoundError(error_message)
    elif "duplicate" in error_message.lower() or "unique constraint" in error_message.lower():
        return DuplicateRecordError(error_message)
    elif "connection" in error_message.lower():
        return DatabaseConnectionError(error_message)
    else:
        return DatabaseError(error_message)


def handle_instagram_api_error(
    response_data: Dict[str, Any],
    status_code: int
) -> InstagramAPIError:
    """Convert Instagram API errors to application exceptions"""
    error_info = response_data.get("error", {})
    
    error_code = error_info.get("code")
    error_type = error_info.get("type", "")
    error_message = error_info.get("message", "Unknown Instagram API error")
    fbtrace_id = error_info.get("fbtrace_id")
    
    # Handle specific error types
    if error_type == "OAuthException" or status_code == 401:
        return InstagramAuthenticationError(
            message=error_message,
            status_code=status_code,
            api_error_code=error_code,
            api_error_type=error_type,
            fbtrace_id=fbtrace_id
        )
    elif status_code == 429:
        return InstagramRateLimitError(
            message=error_message,
            status_code=status_code,
            api_error_code=error_code,
            api_error_type=error_type,
            fbtrace_id=fbtrace_id
        )
    else:
        return InstagramAPIError(
            message=error_message,
            status_code=status_code,
            api_error_code=error_code,
            api_error_type=error_type,
            fbtrace_id=fbtrace_id
        )


def handle_llm_error(error: Exception) -> LLMError:
    """Convert LLM service errors to application exceptions"""
    error_message = str(error)
    
    if "timeout" in error_message.lower():
        return LLMTimeoutError(error_message)
    elif "rate limit" in error_message.lower() or "quota" in error_message.lower():
        return LLMRateLimitError(error_message)
    elif "authentication" in error_message.lower() or "api key" in error_message.lower():
        return LLMAuthenticationError(error_message)
    elif "invalid" in error_message.lower() or "parse" in error_message.lower():
        return LLMInvalidResponseError(error_message)
    else:
        return LLMError(error_message)
