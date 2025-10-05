"""Generate answer use case - handles question answering business logic."""

from typing import Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories.comment import CommentRepository
from ..repositories.answer import AnswerRepository
from ..services.answer_service import QuestionAnswerService
from ..utils.decorators import handle_task_errors
from ..models.question_answer import AnswerStatus


class GenerateAnswerUseCase:
    """Use case for generating answers to question comments."""

    def __init__(self, session: AsyncSession, qa_service=None):
        self.session = session
        self.comment_repo = CommentRepository(session)
        self.answer_repo = AnswerRepository(session)
        self.qa_service = qa_service or QuestionAnswerService()

    @handle_task_errors()
    async def execute(self, comment_id: str, retry_count: int = 0) -> Dict[str, Any]:
        """Execute answer generation use case."""
        # 1. Get comment with classification
        comment = await self.comment_repo.get_with_classification(comment_id)
        if not comment:
            return {"status": "error", "reason": f"Comment {comment_id} not found"}

        # 2. Get or create answer record
        answer_record = await self.answer_repo.get_by_comment_id(comment_id)
        if not answer_record:
            answer_record = await self.answer_repo.create_for_comment(comment_id)

        # 3. Update processing status
        answer_record.processing_status = AnswerStatus.PROCESSING
        answer_record.processing_started_at = datetime.utcnow()
        answer_record.retry_count = retry_count
        await self.session.commit()

        # 4. Generate answer using service
        try:
            answer_result = await self.qa_service.generate_answer(
                question_text=comment.text,
                conversation_id=comment.conversation_id,
                username=comment.username,
            )
        except Exception as exc:
            answer_record.processing_status = AnswerStatus.FAILED
            answer_record.last_error = str(exc)
            await self.session.commit()

            if retry_count < answer_record.max_retries:
                return {"status": "retry", "reason": str(exc)}
            return {"status": "error", "reason": str(exc)}

        # 5. Update answer record with results
        answer_record.answer = answer_result.answer
        answer_record.answer_confidence = answer_result.answer_confidence
        answer_record.answer_quality_score = answer_result.answer_quality_score
        answer_record.llm_raw_response = getattr(answer_result, 'llm_raw_response', None)
        answer_record.input_tokens = answer_result.input_tokens
        answer_record.output_tokens = answer_result.output_tokens
        answer_record.processing_time_ms = answer_result.processing_time_ms
        answer_record.meta_data = getattr(answer_result, 'meta_data', None)
        answer_record.processing_status = AnswerStatus.COMPLETED
        answer_record.processing_completed_at = datetime.utcnow()

        await self.session.commit()

        return {
            "status": "success",
            "answer": answer_result.answer,
            "confidence": answer_result.answer_confidence,
            "quality_score": answer_result.answer_quality_score,
        }
