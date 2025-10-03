import logging
import time
from typing import Any, Dict, Optional

from agents import Runner

from .base_service import BaseService
from ..agents import get_comment_response_agent
from ..config import settings
from ..schemas.answer import AnswerResponse

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
        username: Optional[str] = None,
    ) -> AnswerResponse:
        """Generate answer for customer question with session context."""
        start_time = time.time()

        try:
            # Sanitize input
            sanitized_text = self._sanitize_input(question_text)

            # Add username attribution for multi-user conversation tracking
            if username:
                sanitized_text = f"@{username}: {sanitized_text}"

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

            # Extract token usage if available
            input_tokens = None
            output_tokens = None
            tokens_used = None

            if hasattr(result, 'usage'):
                usage = result.usage
                if usage:
                    input_tokens = getattr(usage, 'input_tokens', None) or getattr(usage, 'prompt_tokens', None)
                    output_tokens = getattr(usage, 'output_tokens', None) or getattr(usage, 'completion_tokens', None)
                    if input_tokens and output_tokens:
                        tokens_used = input_tokens + output_tokens

                    logger.debug(f"Token usage - Input: {input_tokens}, Output: {output_tokens}, Total: {tokens_used}")

            # Fallback to estimation if usage not available
            if tokens_used is None:
                tokens_used = self._estimate_tokens(sanitized_text + answer_result.answer)
                logger.debug(f"Token usage estimated: {tokens_used}")

            return AnswerResponse(
                status="success",
                comment_id=conversation_id or "unknown",
                answer=answer_result.answer,
                answer_confidence=answer_result.confidence,
                answer_quality_score=answer_result.quality_score,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                processing_time_ms=processing_time_ms,
                error=None,
            )

        except Exception as e:
            logger.error(f"Answer generation error: {e}")
            return self._create_error_response(str(e))

    def _create_error_response(self, error_message: str) -> AnswerResponse:
        """Return error response with metadata."""
        return AnswerResponse(
            status="error",
            comment_id="unknown",
            answer=None,
            answer_confidence=0.0,
            answer_quality_score=0,
            processing_time_ms=0,
            error=error_message,
        )
