import logging
from typing import Any, Dict, Optional

from agents import Runner, SQLiteSession

from .base_service import BaseService
from ..agents import comment_classification_agent
from ..config import settings
from ..schemas.classification import ClassificationResponse

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

        # NOTE: Business documents are NOT used in classification
        # They are only used in answer generation (see answer_tasks.py)
        # Classification only needs media context to categorize comments

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
    ) -> ClassificationResponse:
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

            # Extract token usage if available
            input_tokens = None
            output_tokens = None

            if hasattr(result, "usage"):
                usage = result.usage
                if usage:
                    input_tokens = getattr(usage, "input_tokens", None) or getattr(usage, "prompt_tokens", None)
                    output_tokens = getattr(usage, "output_tokens", None) or getattr(usage, "completion_tokens", None)

                    logger.debug(f"Token usage - Input: {input_tokens}, Output: {output_tokens}")

            logger.info(
                f"Classification result: {classification_result.classification} (confidence: {classification_result.confidence})"
            )

            return ClassificationResponse(
                status="success",
                comment_id=conversation_id or "unknown",
                classification=classification_result.classification,
                confidence=classification_result.confidence,
                reasoning=classification_result.reasoning,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                error=None,
            )

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
            if media_context.get("media_context"):
                # AI-analyzed image description
                media_info.append(f"Image analysis: {media_context['media_context'][:500]}...")
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

    def _create_error_response(self, error_message: str) -> ClassificationResponse:
        """Return safe fallback response on classification error."""
        return ClassificationResponse(
            status="error",
            comment_id="unknown",
            classification="spam / irrelevant",  # Safe fallback
            confidence=0,
            reasoning=f"Classification failed: {error_message}",
            error=error_message,
        )
