"""
Instagram Comment Response Agent

This module contains the OpenAI Agent configuration for responding to Instagram comments
into business-relevant categories. The agent is designed to provide accurate and
consistent response with multi-language support.
"""

import logging
from typing import Literal

from agents import Agent
from pydantic import BaseModel, Field

from ..config import settings
from .instructions.instruction_response import RESPONSE_INSTRUCTIONS

logger = logging.getLogger(__name__)


class AnswerResult(BaseModel):
    """Pydantic model for comment response generation results"""

    answer: str = Field(description="The generated answer to the customer's question")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score from 0.0 to 1.0")
    reasoning: str = Field(description="Brief explanation of the answer approach and quality assessment")
    quality_score: int = Field(ge=0, le=100, description="Quality score from 0 to 100")
    is_helpful: bool = Field(description="Whether the answer is likely to be helpful to the customer")
    contains_contact_info: bool = Field(description="Whether the answer includes contact information or next steps")
    tone: Literal["professional", "friendly", "formal", "casual"] = Field(description="The tone of the response")


def create_comment_response_agent() -> Agent:
    """
    Create a comment response generation agent using OpenAI Agents SDK.

    Returns:
        Configured Agent instance for generating customer responses
    """
    # Load instructions from external file for better security and maintainability
    enhanced_instructions = RESPONSE_INSTRUCTIONS

    # Create and return the configured agent
    return Agent(
        name="InstagramCommentResponder",
        instructions=enhanced_instructions,
        output_type=AnswerResult,
        model=settings.openai.model_comment_response,
    )


# Convenience function to get a pre-configured agent
def get_comment_response_agent() -> Agent:
    """
    Get a pre-configured comment response agent using default settings.

    Returns:
        Configured Agent instance for comment response generation
    """
    return create_comment_response_agent()


# Create a singleton instance of the agent
# This ensures only one instance is created and reused throughout the application
comment_response_agent = create_comment_response_agent()
