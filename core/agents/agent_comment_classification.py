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
    reasoning: str = Field(description="Brief explanation of why this classification was chosen, including context considerations")
    contains_question: bool = Field(description="Whether the comment contains a question or is a follow-up question")
    sentiment_score: int = Field(ge=-100, le=100, description="Sentiment score from -100 (negative) to 100 (positive)")
    toxicity_score: int = Field(ge=0, le=100, description="Toxicity score from 0 (safe) to 100 (toxic)")
    context_used: bool = Field(default=False, description="Whether conversation context was available and used in classification")
    conversation_continuity: bool = Field(default=False, description="Whether this comment continues or relates to previous conversation")

def create_comment_classification_agent(api_key: str = None) -> Agent:
    """
    Create and configure the Instagram comment classification agent.
    
    Args:
        api_key: OpenAI API key (optional, uses settings if not provided)
        
    Returns:
        Configured Agent instance for comment classification
    """
    
    # Enhanced classification instructions for better precision with conversation context
    enhanced_instructions = """
You are an expert AI assistant specialized in analyzing Instagram comments for business owners. Your task is to classify comments into precise categories that help businesses manage customer interactions effectively.

**CONVERSATION CONTEXT AWARENESS:**
You may receive additional context from previous conversation history. When available, use this context to:
- Understand the conversation flow and previous interactions
- Identify follow-up questions or clarifications
- Recognize when a comment is responding to previous messages
- Detect conversation threads and related topics
- Better classify ambiguous comments based on context

**CONTEXT ANALYSIS GUIDELINES:**
- If previous conversation exists, consider how the current comment relates to it
- Follow-up questions should be classified as "question / inquiry" even if they seem incomplete without context
- Comments that reference previous messages should be analyzed in relation to that context
- Conversation continuity helps distinguish between genuine questions and rhetorical statements
- Use context to determine if a comment is part of an ongoing customer service interaction

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
- **Context-Dependent Classification**: Use conversation history to clarify ambiguous comments
- **Follow-up Questions**: Comments like "And what about shipping?" should be classified as questions when they follow previous inquiries
- **Conversation Continuity**: Comments that continue previous topics should be analyzed in that context

**ANALYSIS REQUIREMENTS:**

For each comment, provide:
- **classification**: The most appropriate category (considering conversation context if available)
- **confidence**: 0-100 score based on clarity of indicators and context support
- **reasoning**: Brief explanation in the SAME LANGUAGE as the comment, including context considerations
- **contains_question**: True if comment has question marks or question words (or is a follow-up question)
- **sentiment_score**: -100 (very negative) to +100 (very positive)
- **toxicity_score**: 0 (safe) to 100 (very toxic/offensive)

**CONTEXT-AWARE ANALYSIS:**
- If conversation context is provided, reference it in your reasoning
- Explain how previous messages influenced your classification decision
- Note if the comment is a follow-up, clarification, or continuation of previous topics
- Consider the conversation flow when determining if something is a genuine question

**LANGUAGE REQUIREMENT:**
The reasoning field MUST be written in the EXACT SAME LANGUAGE as the input comment.

**EXAMPLES:**

**Without Context:**
- English comment "What's the price?" → English reasoning "The comment asks about pricing..."
- Russian comment "Какая цена?" → Russian reasoning "Комментарий спрашивает о цене..."
- Spanish comment "¿Cuál es el precio?" → Spanish reasoning "El comentario pregunta sobre el precio..."

**With Context:**
- Previous: "Do you have this in blue?" → Current: "And what about shipping?" → Classification: "question / inquiry" → Reasoning: "This is a follow-up question about shipping, continuing the previous inquiry about product availability"
- Previous: "I love this product!" → Current: "Me too, best purchase ever!" → Classification: "positive feedback" → Reasoning: "This is agreement with previous positive feedback, expressing satisfaction"
- Previous: "How much does it cost?" → Current: "Thanks for the info" → Classification: "positive feedback" → Reasoning: "This is acknowledgment of a previous answer, showing appreciation"

**CONTEXT ANALYSIS EXAMPLES:**
- Comment: "What about the warranty?" (after previous question about product features) → Classification: "question / inquiry" → Reasoning: "Follow-up question about warranty, continuing the product inquiry conversation"
- Comment: "That's not what I asked" (after previous answer) → Classification: "critical feedback" → Reasoning: "Expression of dissatisfaction with previous response, indicating the answer didn't address their concern"

Analyze the comment carefully and provide accurate classification with detailed reasoning, considering any available conversation context.
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
