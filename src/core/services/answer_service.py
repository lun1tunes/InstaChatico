import logging
import time
from typing import Any, Dict, Optional

from agents import Runner

from .base_service import BaseService
from ..agents import get_comment_response_agent
from ..config import settings

logger = logging.getLogger(__name__)


class QuestionAnswerService(BaseService):
    """Generate answers using OpenAI Agents SDK, reuses sessions from classification."""

    def __init__(
        self, api_key: str = None, db_path: str = "conversations/conversations.db"
    ):
        super().__init__(db_path)
        self.api_key = api_key or settings.openai.api_key
        self.response_agent = get_comment_response_agent()

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
