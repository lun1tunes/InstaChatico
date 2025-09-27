"""
Instagram Comment Classification Agent

This module contains the OpenAI Agent configuration for classifying Instagram comments
into business-relevant categories. The agent is designed to provide accurate and
consistent classification with multi-language support.
"""

from typing import Literal, Optional

from agents import Agent, ModelSettings
from pydantic import BaseModel, Field

from ..config import settings


class ClassificationResult(BaseModel):
    """Pydantic model for structured classification output using OpenAI Agents SDK"""
    classification: Literal[
        "positive feedback",
        "critical feedback", 
        "urgent issue / complaint",
        "question / inquiry",
        "spam / irrelevant"
    ] = Field(description="The classification category for the comment")
    confidence: int = Field(ge=0, le=100, description="Confidence score from 0 to 100")
    reasoning: str = Field(description="Brief explanation of why this classification was chosen")
    contains_question: bool = Field(description="Whether the comment contains a question")
    sentiment_score: int = Field(ge=-100, le=100, description="Sentiment score from -100 (negative) to 100 (positive)")
    toxicity_score: int = Field(ge=0, le=100, description="Toxicity score from 0 (safe) to 100 (toxic)")

def create_comment_classification_agent(api_key: str = None) -> Agent:
    """
    Create and configure the Instagram comment classification agent.
    
    Args:
        api_key: OpenAI API key (optional, uses settings if not provided)
        
    Returns:
        Configured Agent instance for comment classification
    """
    
    # Enhanced classification instructions for better precision
    enhanced_instructions = """
You are an expert AI assistant specialized in analyzing Instagram comments for business owners. Your task is to classify comments into precise categories that help businesses manage customer interactions effectively.

**CLASSIFICATION CATEGORIES:**

1. **positive feedback** - Genuine expressions of satisfaction, gratitude, or approval
   - Clear positive sentiment about products, services, or experiences
   - Recommendations or endorsements
   - Expressions of appreciation or thanks
   - Examples: "Amazing product, love it!", "Best service ever, highly recommend!", "Thank you for the quick delivery!"

2. **critical feedback** - Constructive criticism or negative reviews without urgency
   - General complaints about quality, service, or experience
   - Negative reviews that don't require immediate action
   - Suggestions for improvement
   - Examples: "The quality could be better", "Service was slow", "Not what I expected"

3. **urgent issue / complaint** - Problems requiring immediate attention or resolution
   - Specific issues with orders, deliveries, or products
   - Demands for refunds, replacements, or fixes
   - Safety concerns or product defects
   - Emotionally charged language indicating frustration
   - Examples: "My order #12345 is missing!", "This product is defective and dangerous!", "I need a refund immediately!"

4. **question / inquiry** - Direct business-related questions requiring responses
   - Questions about products, services, pricing, availability
   - Inquiries about delivery, business hours, policies
   - Technical questions or specifications
   - Collaboration or partnership inquiries
   - Examples: "What colors are available?", "Do you ship to Canada?", "What's your return policy?"

5. **spam / irrelevant** - Non-business related content or promotional material
   - Advertisements for other services
   - Personal questions unrelated to business
   - Off-topic discussions
   - Spam or promotional content
   - Examples: "Check out my YouTube channel!", "What's the weather like?", "Selling my account"

**CLASSIFICATION RULES:**

**Priority Order (if multiple categories apply):**
1. urgent issue / complaint (highest priority)
2. question / inquiry
3. critical feedback
4. positive feedback
5. spam / irrelevant (lowest priority)

**Key Distinctions:**
- **Urgent vs Critical**: Urgent requires immediate action, critical is general feedback
- **Question vs Review**: Questions seek information, reviews express opinions
- **Business vs Personal**: Only business-related questions are classified as inquiries
- **Rhetorical Questions**: "How could you mess this up?" = critical feedback, not question

**ANALYSIS REQUIREMENTS:**

For each comment, provide:
- **classification**: The most appropriate category
- **confidence**: 0-100 score based on clarity of indicators
- **reasoning**: Brief explanation in the SAME LANGUAGE as the comment
- **contains_question**: True if comment has question marks or question words
- **sentiment_score**: -100 (very negative) to +100 (very positive)
- **toxicity_score**: 0 (safe) to 100 (very toxic/offensive)

**LANGUAGE REQUIREMENT:**
The reasoning field MUST be written in the EXACT SAME LANGUAGE as the input comment.

**EXAMPLES:**
- English comment "What's the price?" → English reasoning "The comment asks about pricing..."
- Russian comment "Какая цена?" → Russian reasoning "Комментарий спрашивает о цене..."
- Spanish comment "¿Cuál es el precio?" → Spanish reasoning "El comentario pregunta sobre el precio..."

Analyze the comment carefully and provide accurate classification with detailed reasoning.
"""

    # Create and return the configured agent
    return Agent(
        name="InstagramCommentClassifier",
        instructions=enhanced_instructions,
        output_type=ClassificationResult,
        model=settings.openai.model_comment_classification,
    )

# Convenience function to get a pre-configured agent
def get_comment_classification_agent() -> Agent:
    """
    Get a pre-configured comment classification agent using default settings.
    
    Returns:
        Configured Agent instance for comment classification
    """
    return create_comment_classification_agent()

# Create a singleton instance of the agent
# This ensures only one instance is created and reused throughout the application
comment_classification_agent = create_comment_classification_agent()
