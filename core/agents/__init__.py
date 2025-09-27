# OpenAI Agents SDK integration for Instagram comment classification

from .agent_comment_classification import (
    create_comment_classification_agent,
    get_comment_classification_agent,
    comment_classification_agent,  # Singleton instance
    ClassificationResult
)

__all__ = [
    "create_comment_classification_agent",
    "get_comment_classification_agent",
    "comment_classification_agent",  # Singleton instance
    "ClassificationResult"
]