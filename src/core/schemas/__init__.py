"""Core Pydantic schemas for the application."""

from .classification import (
    ClassificationRequest,
    ClassificationResponse,
    ClassificationResultData,
)
from .answer import (
    AnswerRequest,
    AnswerResponse,
    AnswerResultData,
)
from .webhook import (
    WebhookProcessingResponse,
    TestCommentResponse,
)

__all__ = [
    "ClassificationRequest",
    "ClassificationResponse",
    "ClassificationResultData",
    "AnswerRequest",
    "AnswerResponse",
    "AnswerResultData",
    "WebhookProcessingResponse",
    "TestCommentResponse",
]
