import time
import os
import logging
from typing import Any, Dict, Optional
from pathlib import Path

from agents import Runner, SQLiteSession
from ..config import settings
from ..agents import comment_response_agent, get_comment_response_agent

comment_response_agent = get_comment_response_agent()
logger = logging.getLogger(__name__)


class QuestionAnswerService:
    """Generate answers using OpenAI Agents SDK, reuses sessions from classification.

    Media context and conversation history loaded automatically from SQLiteSession.
    """

    def __init__(
        self, api_key: str = None, db_path: str = "conversations/conversations.db"
    ):
        self.api_key = api_key or settings.openai.api_key
        self.response_agent = comment_response_agent
        self.db_path = db_path
        self._ensure_db_directory()

    def _ensure_db_directory(self):
        """Create conversations database directory if needed."""
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Conversations database will be stored at: {self.db_path}")

    def _get_session(self, conversation_id: str) -> SQLiteSession:
        """Retrieve existing session with full conversation history."""
        logger.debug(
            f"🔄 Retrieving existing SQLiteSession for conversation_id: {conversation_id}"
        )
        logger.debug(f"📂 Session database path: {self.db_path}")

        # SQLiteSession automatically loads existing data from the database
        session = SQLiteSession(conversation_id, self.db_path)

        logger.debug(
            f"✅ SQLiteSession retrieved successfully for conversation: {conversation_id}"
        )
        logger.debug(
            f"💡 Session will include all previous messages and media context automatically"
        )
        return session

    async def generate_answer(
        self,
        question_text: str,
        conversation_id: Optional[str] = None,
        media_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate answer for customer question with session context."""
        start_time = time.time()

        try:
            # Sanitize input
            sanitized_text = self._sanitize_input(question_text)

            if len(sanitized_text) > 1000:
                sanitized_text = sanitized_text[:1000] + "..."

            # Use session if conversation_id is provided
            if conversation_id:
                logger.debug(
                    f"Starting answer generation with persistent session for conversation_id: {conversation_id}"
                )
                # Use SQLiteSession (media context already injected by classification service)
                session = self._get_session(conversation_id)
                result = await Runner.run(
                    self.response_agent, input=sanitized_text, session=session
                )
                logger.info(
                    f"Answer generated successfully using SQLiteSession for conversation: {conversation_id}"
                )
            else:
                logger.debug(
                    "Starting answer generation without session (stateless mode)"
                )
                # Use regular Runner without session
                result = await Runner.run(self.response_agent, input=sanitized_text)
                logger.info("Answer generated successfully without session")

            answer_result = result.final_output
            processing_time_ms = int((time.time() - start_time) * 1000)

            return {
                "answer": answer_result.answer,
                "confidence": answer_result.confidence,
                "quality_score": answer_result.quality_score,
                "tokens_used": self._estimate_tokens(
                    sanitized_text + answer_result.answer
                ),
                "processing_time_ms": processing_time_ms,
                "llm_raw_response": str(result),
                "conversation_id": conversation_id,
                "session_used": conversation_id is not None,
                "meta_data": {
                    "question_length": len(question_text),
                    "answer_length": len(answer_result.answer),
                    "model_used": settings.openai.model_comment_response,
                    "reasoning": answer_result.reasoning,
                    "is_helpful": answer_result.is_helpful,
                    "contains_contact_info": answer_result.contains_contact_info,
                    "tone": answer_result.tone,
                },
            }

        except Exception as e:
            logger.error(f"Answer generation error: {e}")
            return self._create_error_response(str(e))

    def _sanitize_input(self, text: str) -> str:
        """Escape HTML and normalize whitespace."""
        import html

        sanitized = html.escape(text)
        sanitized = " ".join(sanitized.split())
        return sanitized

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count (~4 chars per token)."""
        return len(text) // 4

    def _create_error_response(self, error_message: str) -> Dict[str, Any]:
        """Return error response with metadata."""
        return {
            "answer": None,
            "confidence": 0.0,
            "quality_score": 0,
            "tokens_used": 0,
            "processing_time_ms": 0,
            "error": error_message,
            "meta_data": {"error": True},
        }

    def get_conversation_history(self, conversation_id: str) -> list:
        """Get conversation history (handled internally by SQLiteSession)."""
        # SQLiteSession from OpenAI Agents SDK doesn't expose conversation history
        # The session is used internally by the agent for context management
        logger.debug(
            f"Conversation history is managed internally by SQLiteSession for: {conversation_id}"
        )
        return []

    def clear_conversation(self, conversation_id: str) -> bool:
        """Clear conversation (managed internally by SQLiteSession)."""
        # SQLiteSession from OpenAI Agents SDK manages conversation history internally
        # We cannot directly clear the history, but the session will be recreated for new conversations
        logger.debug(
            f"Conversation history is managed internally by SQLiteSession for: {conversation_id}"
        )
        return True

    def get_session_info(self, conversation_id: str) -> Dict[str, Any]:
        """Get basic session info (history managed internally by SDK)."""
        try:
            logger.debug(
                f"Getting session information for conversation_id: {conversation_id}"
            )
            session = self._get_session(conversation_id)

            # SQLiteSession from OpenAI Agents SDK manages conversation history internally
            # We can only provide basic session information
            session_info = {
                "conversation_id": conversation_id,
                "db_path": self.db_path,
                "session_exists": True,
                "history_count": 0,  # Cannot access history count directly
                "note": "Conversation history is managed internally by SQLiteSession",
            }
            logger.debug(f"Session info retrieved for conversation: {conversation_id}")
            return session_info
        except Exception as e:
            logger.error(f"Error getting session info for {conversation_id}: {e}")
            return {
                "conversation_id": conversation_id,
                "db_path": self.db_path,
                "session_exists": False,
                "error": str(e),
            }
