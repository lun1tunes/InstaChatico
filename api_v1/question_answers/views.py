from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from typing import List, Optional

from core.models import QuestionAnswer, InstagramComment, CommentClassification, AnswerStatus, ProcessingStatus
from core.models.db_helper import db_helper

router = APIRouter(tags=["question-answers"])


@router.get("/comment/{comment_id}")
async def get_answer_by_comment(comment_id: str, session: AsyncSession = Depends(db_helper.scoped_session_dependency)):
    """Get answer for a specific comment"""
    result = await session.execute(
        select(QuestionAnswer)
        .options(selectinload(QuestionAnswer.classification))
        .where(QuestionAnswer.comment_id == comment_id)
    )
    answer = result.scalar_one_or_none()

    if not answer:
        raise HTTPException(status_code=404, detail="Answer not found")

    return {
        "comment_id": answer.comment_id,
        "status": answer.processing_status,
        "answer": answer.answer,
        "confidence": answer.answer_confidence,
        "quality_score": answer.answer_quality_score,
        "processing_started_at": answer.processing_started_at,
        "processing_completed_at": answer.processing_completed_at,
        "retry_count": answer.retry_count,
        "last_error": answer.last_error,
        "tokens_used": answer.tokens_used,
        "processing_time_ms": answer.processing_time_ms,
        "meta_data": answer.meta_data,
    }


@router.get("/")
async def list_answers(
    status: Optional[AnswerStatus] = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
):
    """List all question answers with optional filtering"""
    query = select(QuestionAnswer).options(selectinload(QuestionAnswer.classification))

    if status:
        query = query.where(QuestionAnswer.processing_status == status)

    query = query.offset(offset).limit(limit).order_by(QuestionAnswer.id.desc())

    result = await session.execute(query)
    answers = result.scalars().all()

    return [
        {
            "id": answer.id,
            "comment_id": answer.comment_id,
            "status": answer.processing_status,
            "answer": answer.answer,
            "confidence": answer.answer_confidence,
            "quality_score": answer.answer_quality_score,
            "processing_started_at": answer.processing_started_at,
            "processing_completed_at": answer.processing_completed_at,
            "retry_count": answer.retry_count,
            "last_error": answer.last_error,
            "tokens_used": answer.tokens_used,
            "processing_time_ms": answer.processing_time_ms,
        }
        for answer in answers
    ]


@router.get("/stats")
async def get_answer_stats(session: AsyncSession = Depends(db_helper.scoped_session_dependency)):
    """Get statistics about question answers"""
    from sqlalchemy import func

    # Total counts by status
    status_counts = await session.execute(
        select(QuestionAnswer.processing_status, func.count(QuestionAnswer.id).label("count")).group_by(
            QuestionAnswer.processing_status
        )
    )
    status_stats = {row.processing_status: row.count for row in status_counts}

    # Average metrics for completed answers
    completed_stats = await session.execute(
        select(
            func.avg(QuestionAnswer.answer_confidence).label("avg_confidence"),
            func.avg(QuestionAnswer.answer_quality_score).label("avg_quality"),
            func.avg(QuestionAnswer.tokens_used).label("avg_tokens"),
            func.avg(QuestionAnswer.processing_time_ms).label("avg_processing_time"),
            func.count(QuestionAnswer.id).label("total_completed"),
        ).where(QuestionAnswer.processing_status == AnswerStatus.COMPLETED)
    )

    completed_row = completed_stats.first()

    return {
        "status_counts": status_stats,
        "completed_stats": {
            "total_completed": completed_row.total_completed or 0,
            "average_confidence": round(completed_row.avg_confidence or 0, 3),
            "average_quality_score": round(completed_row.avg_quality or 0, 1),
            "average_tokens_used": round(completed_row.avg_tokens or 0, 1),
            "average_processing_time_ms": round(completed_row.avg_processing_time or 0, 1),
        },
    }


@router.post("/retry/{comment_id}")
async def retry_answer_generation(
    comment_id: str, session: AsyncSession = Depends(db_helper.scoped_session_dependency)
):
    """Manually retry answer generation for a comment"""
    from core.tasks.answer_tasks import generate_answer_async
    import asyncio

    # Check if comment exists and is classified as a question
    result = await session.execute(
        select(InstagramComment)
        .options(selectinload(InstagramComment.classification))
        .where(InstagramComment.id == comment_id)
    )
    comment = result.scalar_one_or_none()

    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    if not comment.classification:
        raise HTTPException(status_code=400, detail="Comment has no classification")

    if comment.classification.classification.lower() != "question / inquiry":
        raise HTTPException(status_code=400, detail="Comment is not classified as a question")

    # Run the answer generation directly
    result = await generate_answer_async(comment_id)

    return {"status": "completed", "comment_id": comment_id, "result": result}


@router.post("/process-pending")
async def process_pending_questions(session: AsyncSession = Depends(db_helper.scoped_session_dependency)):
    """Process all pending questions that don't have answers yet"""
    from core.tasks.answer_tasks import generate_answer_async
    import asyncio

    # Find comments classified as questions that don't have answers
    result = await session.execute(
        select(InstagramComment)
        .options(selectinload(InstagramComment.classification))
        .join(CommentClassification)
        .outerjoin(QuestionAnswer)
        .where(
            and_(
                CommentClassification.classification == "question / inquiry",
                CommentClassification.processing_status == ProcessingStatus.COMPLETED,
                QuestionAnswer.id.is_(None),
            )
        )
    )
    pending_comments = result.scalars().all()

    processed_count = 0
    results = []

    for comment in pending_comments:
        try:
            result = await generate_answer_async(comment.id)
            results.append({"comment_id": comment.id, "status": "success", "result": result})
            processed_count += 1
        except Exception as e:
            results.append({"comment_id": comment.id, "status": "error", "error": str(e)})

    return {
        "status": "completed",
        "processed_count": processed_count,
        "total_found": len(pending_comments),
        "results": results,
    }
