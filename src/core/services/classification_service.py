import logging
from typing import Any, Dict, Optional

from agents import Runner, SQLiteSession

from .base_service import BaseService
from ..agents import comment_classification_agent
from ..config import settings

logger = logging.getLogger(__name__)


class CommentClassificationService(BaseService):
    """Classify Instagram comments using OpenAI Agents SDK with persistent sessions."""

    def __init__(self, api_key: str = None, db_path: str = "conversations/conversations.db"):
        super().__init__(db_path)
        self.api_key = api_key or settings.openai.api_key
        self.classification_agent = comment_classification_agent

    async def _get_session_with_media_context(
        self, conversation_id: str, media_context: Optional[Dict[str, Any]] = None
    ) -> SQLiteSession:
        """Get or create session, inject media context once on first message."""
        logger.debug(f"Creating/retrieving SQLiteSession for conversation_id: {conversation_id}")
        logger.debug(f"Session database path: {self.db_path}")
        session = SQLiteSession(conversation_id, self.db_path)

        # Check if this is a new conversation by checking if it has any history
        # According to OpenAI Agents SDK docs, SQLiteSession automatically manages persistence
        try:
            # Get the session's current state to check if it's new
            # If session has no items, it's a new conversation - add media context
            if media_context and not await self._session_has_context(conversation_id):
                await self._inject_media_context_to_session(session, media_context)
                logger.info(f"✅ Media context injected into NEW conversation: {conversation_id}")
            elif media_context:
                logger.debug(
                    f"⏭️  Skipping media context injection - conversation {conversation_id} already has context"
                )
        except Exception as e:
            logger.warning(f"Failed to check/inject media context: {e} - continuing without context")

        logger.debug(f"SQLiteSession retrieved successfully for conversation: {conversation_id}")
        return session

    async def _session_has_context(self, conversation_id: str) -> bool:
        """Check if session has existing messages in agent_messages table."""
        has_messages = await self._session_has_messages(conversation_id)
        if has_messages:
            logger.debug(f"Session {conversation_id} has existing messages - skipping context")
        else:
            logger.debug(f"Session {conversation_id} is new - will inject context")
        return has_messages

    async def _inject_media_context_to_session(self, session: SQLiteSession, media_context: Dict[str, Any]) -> None:
        """Add media context as system message to new conversation."""
        try:
            # Create a comprehensive media description
            media_description = self._create_media_description(media_context)

            # Add media context as a system message to the session
            # According to OpenAI Agents SDK docs, this will be persisted and available
            # throughout the conversation lifecycle
            await session.add_items(
                [
                    {
                        "role": "system",
                        "content": f"📋 MEDIA CONTEXT (Post Information):\n{media_description}\n\nUse this context when analyzing comments and generating responses.",
                    }
                ]
            )

            logger.info(f"✅ Injected media context into session: {media_description[:150]}...")

        except Exception as e:
            logger.error(f"❌ Failed to inject media context into session: {e}")

    def _create_media_description(self, media_context: Dict[str, Any]) -> str:
        """Format media context into readable description."""
        description_parts = []

        # Basic media info
        if media_context.get("media_type"):
            description_parts.append(f"Post Type: {media_context['media_type']}")

        if media_context.get("username"):
            description_parts.append(f"Author: @{media_context['username']}")

        # Post content
        if media_context.get("caption"):
            caption = media_context["caption"]
            # Truncate long captions but keep important info
            if len(caption) > 500:
                caption = caption[:500] + "..."
            description_parts.append(f"Post Caption: {caption}")

        if media_context.get("media_url"):
            description_parts.append(f"Media URL: {media_context['media_url']}")

        # Engagement metrics
        engagement_parts = []
        if media_context.get("comments_count") is not None:
            engagement_parts.append(f"{media_context['comments_count']} comments")
        if media_context.get("like_count") is not None:
            engagement_parts.append(f"{media_context['like_count']} likes")

        if engagement_parts:
            description_parts.append(f"Engagement: {', '.join(engagement_parts)}")

        # Additional context
        if media_context.get("is_comment_enabled") is not None:
            status = "enabled" if media_context["is_comment_enabled"] else "disabled"
            description_parts.append(f"Comments: {status}")

        if media_context.get("permalink"):
            description_parts.append(f"Post URL: {media_context['permalink']}")

        return "\n".join(description_parts)

    def _generate_conversation_id(self, comment_id: str, parent_id: Optional[str] = None) -> str:
        """Generate conversation ID: first_question_comment_{parent_id or comment_id}."""
        if parent_id:
            # If this is a reply, use the parent's conversation ID
            return f"first_question_comment_{parent_id}"
        else:
            # If this is a top-level comment, use its own ID
            return f"first_question_comment_{comment_id}"

    async def classify_comment(
        self,
        comment_text: str,
        conversation_id: Optional[str] = None,
        media_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Classify comment using OpenAI agent with optional session context."""
        try:
            # Format input with conversation and media context
            formatted_input = self._format_input_with_context(comment_text, conversation_id, media_context)

            if len(formatted_input) > 2000:  # Increased limit for context
                formatted_input = formatted_input[:2000] + "..."
                logger.warning(f"Input truncated to 2000 characters: {comment_text[:50]}...")

            logger.info(f"Classifying comment with context: {formatted_input[:200]}...")

            # Use session if conversation_id is provided
            if conversation_id:
                logger.debug(f"Starting classification with persistent session for conversation_id: {conversation_id}")
                # Use SQLiteSession with media context for persistent conversation
                session = await self._get_session_with_media_context(conversation_id, media_context)
                result = await Runner.run(self.classification_agent, input=formatted_input, session=session)
                logger.info(
                    f"Classification completed using SQLiteSession with media context for conversation: {conversation_id}"
                )
            else:
                logger.debug("Starting classification without session (stateless mode)")
                # Use regular Runner without session
                result = await Runner.run(self.classification_agent, input=formatted_input)
                logger.info("Classification completed without session")

            # Extract the final output from the result
            classification_result = result.final_output

            logger.info(
                f"Classification result: {classification_result.classification} (confidence: {classification_result.confidence})"
            )

            return {
                "classification": classification_result.classification,
                "confidence": classification_result.confidence,
                "contains_question": classification_result.contains_question,
                "sentiment_score": classification_result.sentiment_score,
                "toxicity_score": classification_result.toxicity_score,
                "reasoning": classification_result.reasoning,
                "context_used": classification_result.context_used,
                "conversation_continuity": classification_result.conversation_continuity,
                "llm_raw_response": str(classification_result),
                "conversation_id": conversation_id,
                "session_used": conversation_id is not None,
                "error": None,
            }

        except Exception as e:
            logger.error(f"Classification error: {e}")
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")
            return self._create_error_response(str(e))

    def _format_input_with_context(
        self,
        comment_text: str,
        conversation_id: Optional[str] = None,
        media_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Format comment with media context and conversation info."""
        sanitized_text = self._sanitize_input(comment_text)

        # Build context information
        context_parts = []

        # Add media context if available
        if media_context:
            media_info = []
            if media_context.get("caption"):
                media_info.append(f"Post caption: {media_context['caption'][:200]}...")
            if media_context.get("media_type"):
                media_info.append(f"Post type: {media_context['media_type']}")
            if media_context.get("username"):
                media_info.append(f"Post author: @{media_context['username']}")
            if media_context.get("comments_count") is not None:
                media_info.append(f"Post has {media_context['comments_count']} comments")
            if media_context.get("like_count") is not None:
                media_info.append(f"Post has {media_context['like_count']} likes")

            if media_info:
                context_parts.append("Media context:")
                context_parts.extend(media_info)

        # Add conversation context if available
        if conversation_id:
            context_parts.append(f"Conversation ID: {conversation_id}")

        # Combine all context
        if context_parts:
            context_text = "\n".join(context_parts)
            formatted_input = f"{context_text}\n\nComment to classify: {sanitized_text}"
            logger.debug(f"Formatted input with context: {formatted_input[:200]}...")
            return formatted_input

        # Return sanitized text without context
        return sanitized_text

    def _create_error_response(self, error_message: str) -> Dict[str, Any]:
        """Return safe fallback response on classification error."""
        return {
            "classification": "spam / irrelevant",  # Safe fallback
            "confidence": 0,
            "contains_question": False,
            "sentiment_score": 0,
            "toxicity_score": 0,
            "reasoning": f"Classification failed: {error_message}",
            "context_used": False,
            "conversation_continuity": False,
            "llm_raw_response": None,
            "error": error_message,
        }

    def _detect_question(self, text: str) -> bool:
        """Detect questions in multiple languages (EN, RU, ES, FR, DE)."""
        question_indicators = [
            # English
            "?",
            "what",
            "how",
            "when",
            "where",
            "why",
            "who",
            "which",
            "can",
            "could",
            "would",
            "should",
            # Russian
            "как",
            "что",
            "где",
            "когда",
            "почему",
            "зачем",
            "кто",
            "какой",
            "можете",
            "можно",
            # Spanish
            "qué",
            "cómo",
            "cuándo",
            "dónde",
            "por qué",
            "quién",
            "cuál",
            "puede",
            "puedo",
            # French
            "quoi",
            "comment",
            "quand",
            "où",
            "pourquoi",
            "qui",
            "peut",
            "peux",
            # German
            "was",
            "wie",
            "wann",
            "wo",
            "warum",
            "wer",
            "kann",
            "können",
        ]
        text_lower = text.lower()
        return any(indicator in text_lower for indicator in question_indicators)

    def _estimate_sentiment(self, classification: str, confidence: int) -> int:
        """Estimate sentiment score (-100 to 100) from classification."""
        sentiment_map = {
            "positive feedback": confidence,
            "critical feedback": -confidence,
            "urgent issue / complaint": -confidence - 20,  # More negative for urgent issues
            "question / inquiry": 0,  # Neutral for questions
            "partnership proposal": confidence // 2,  # Mildly positive (business opportunity)
            "toxic / abusive": -100,  # Most negative
            "spam / irrelevant": -50,
            "unknown": 0,
        }
        return max(-100, min(100, sentiment_map.get(classification, 0)))

    def _estimate_toxicity(self, classification: str, confidence: int) -> int:
        """Estimate toxicity score (0 to 100) from classification."""
        if classification == "toxic / abusive":
            return 100  # Highest toxicity
        elif classification in ["critical feedback", "urgent issue / complaint"]:
            return min(100, confidence + 20)
        elif classification == "spam / irrelevant":
            return 60
        elif classification in ["positive feedback", "partnership proposal"]:
            return 0  # No toxicity
        return 10  # Low toxicity for questions
