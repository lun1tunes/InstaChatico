"""Instagram comment management endpoints."""

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.models import db_helper
from core.models.instagram_comment import InstagramComment
from core.models.comment_classification import CommentClassification
from core.models.question_answer import QuestionAnswer
from core.repositories.comment import CommentRepository
from core.schemas.comment import (
    CommentDetailResponse,
    CommentWithClassificationResponse,
    CommentWithAnswerResponse,
    CommentFullResponse,
    HideCommentResponse,
    UnhideCommentResponse,
    SendReplyResponse,
    CommentListResponse,
    CommentListItem,
)
from core.use_cases.hide_comment import HideCommentUseCase
from core.dependencies import get_hide_comment_use_case, get_comment_repository
from core.container import get_container, Container
from core.utils.time import now_db_utc

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Comments"], prefix="/comments")


# ============================================================================
# Comment Retrieval Endpoints
# ============================================================================


@router.get("/{comment_id}", response_model=CommentDetailResponse)
async def get_comment(
    comment_id: str,
    comment_repo: CommentRepository = Depends(get_comment_repository),
):
    """
    Get basic comment information with hiding status.

    Returns:
        CommentDetailResponse with id, text, username, hiding status, etc.
    """
    comment = await comment_repo.get_by_id(comment_id)

    if not comment:
        raise HTTPException(status_code=404, detail=f"Comment {comment_id} not found")

    return CommentDetailResponse.model_validate(comment)


@router.get("/{comment_id}/classification", response_model=CommentWithClassificationResponse)
async def get_comment_with_classification(
    comment_id: str,
    comment_repo: CommentRepository = Depends(get_comment_repository),
):
    """
    Get comment with classification details.

    Returns:
        CommentWithClassificationResponse including classification, confidence, reasoning, tokens
    """
    comment = await comment_repo.get_with_classification(comment_id)

    if not comment:
        raise HTTPException(status_code=404, detail=f"Comment {comment_id} not found")

    # Build response from comment and classification
    response_data = {
        **CommentDetailResponse.model_validate(comment).model_dump(),
    }

    if comment.classification:
        response_data.update(
            {
                "classification": comment.classification.classification,
                "confidence": comment.classification.confidence,
                "reasoning": comment.classification.reasoning,
                "input_tokens": comment.classification.input_tokens,
                "output_tokens": comment.classification.output_tokens,
                "processing_status": (
                    comment.classification.processing_status.value if comment.classification.processing_status else None
                ),
                "processing_started_at": comment.classification.processing_started_at,
                "processing_completed_at": comment.classification.processing_completed_at,
            }
        )

    return CommentWithClassificationResponse(**response_data)


@router.get("/{comment_id}/answer", response_model=CommentWithAnswerResponse)
async def get_comment_with_answer(
    comment_id: str,
    comment_repo: CommentRepository = Depends(get_comment_repository),
):
    """
    Get comment with answer details.

    Returns:
        CommentWithAnswerResponse including answer, confidence, quality score, tokens
    """
    comment = await comment_repo.get_with_answer(comment_id)

    if not comment:
        raise HTTPException(status_code=404, detail=f"Comment {comment_id} not found")

    # Build response
    response_data = {
        **CommentDetailResponse.model_validate(comment).model_dump(),
    }

    if comment.question_answer:
        response_data.update(
            {
                "answer": comment.question_answer.answer,
                "answer_confidence": comment.question_answer.answer_confidence,
                "answer_quality_score": comment.question_answer.answer_quality_score,
                "input_tokens": comment.question_answer.input_tokens,
                "output_tokens": comment.question_answer.output_tokens,
                "processing_status": (
                    comment.question_answer.processing_status.value
                    if comment.question_answer.processing_status
                    else None
                ),
                "processing_started_at": comment.question_answer.processing_started_at,
                "processing_completed_at": comment.question_answer.processing_completed_at,
            }
        )

    return CommentWithAnswerResponse(**response_data)


@router.get("/{comment_id}/full", response_model=CommentFullResponse)
async def get_comment_full(
    comment_id: str,
    comment_repo: CommentRepository = Depends(get_comment_repository),
):
    """
    Get complete comment information with classification, answer, and reply status.

    Returns:
        CommentFullResponse with all available data about the comment
    """
    comment = await comment_repo.get_full(comment_id)

    if not comment:
        raise HTTPException(status_code=404, detail=f"Comment {comment_id} not found")

    # Build comprehensive response
    response_data = {
        **CommentDetailResponse.model_validate(comment).model_dump(),
    }

    # Add classification data
    if comment.classification:
        response_data.update(
            {
                "classification": comment.classification.classification,
                "confidence": comment.classification.confidence,
                "reasoning": comment.classification.reasoning,
                "classification_status": (
                    comment.classification.processing_status.value if comment.classification.processing_status else None
                ),
                "classification_started_at": comment.classification.processing_started_at,
                "classification_completed_at": comment.classification.processing_completed_at,
                "classification_input_tokens": comment.classification.input_tokens,
                "classification_output_tokens": comment.classification.output_tokens,
            }
        )

    # Add answer and reply data
    if comment.question_answer:
        response_data.update(
            {
                "answer": comment.question_answer.answer,
                "answer_confidence": comment.question_answer.answer_confidence,
                "answer_quality_score": comment.question_answer.answer_quality_score,
                "answer_status": (
                    comment.question_answer.processing_status.value
                    if comment.question_answer.processing_status
                    else None
                ),
                "answer_started_at": comment.question_answer.processing_started_at,
                "answer_completed_at": comment.question_answer.processing_completed_at,
                "answer_input_tokens": comment.question_answer.input_tokens,
                "answer_output_tokens": comment.question_answer.output_tokens,
                "answer_processing_time_ms": comment.question_answer.processing_time_ms,
                "reply_sent": comment.question_answer.reply_sent,
                "reply_sent_at": comment.question_answer.reply_sent_at,
                "reply_status": comment.question_answer.reply_status,
                "reply_id": comment.question_answer.reply_id,
            }
        )

    return CommentFullResponse(**response_data)


@router.get("/", response_model=CommentListResponse)
async def list_comments(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    classification: str | None = Query(None, description="Filter by classification"),
    is_hidden: bool | None = Query(None, description="Filter by hidden status"),
    has_reply: bool | None = Query(None, description="Filter by reply status"),
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
):
    """
    List comments with pagination and filters.

    Args:
        page: Page number (1-indexed)
        page_size: Number of items per page (max 100)
        classification: Filter by classification category
        is_hidden: Filter by hidden status
        has_reply: Filter by whether reply was sent

    Returns:
        CommentListResponse with paginated comments
    """
    # Build query with filters
    query = select(InstagramComment).options(
        selectinload(InstagramComment.classification), selectinload(InstagramComment.question_answer)
    )

    if is_hidden is not None:
        query = query.where(InstagramComment.is_hidden == is_hidden)

    if classification is not None:
        query = query.join(InstagramComment.classification).where(
            CommentClassification.classification == classification
        )

    if has_reply is not None:
        query = query.join(InstagramComment.question_answer).where(QuestionAnswer.reply_sent == has_reply)

    # Order by created_at descending (newest first)
    query = query.order_by(InstagramComment.created_at.desc())

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar()

    # Paginate
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await session.execute(query)
    comments = result.scalars().all()

    # Build response items
    comment_items = []
    for comment in comments:
        item_data = {
            **CommentDetailResponse.model_validate(comment).model_dump(),
        }

        if comment.classification:
            item_data.update(
                {
                    "classification": comment.classification.classification,
                    "confidence": comment.classification.confidence,
                }
            )

        if comment.question_answer:
            item_data["reply_sent"] = comment.question_answer.reply_sent

        comment_items.append(CommentListItem(**item_data))

    total_pages = (total + page_size - 1) // page_size

    return CommentListResponse(
        comments=comment_items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# ============================================================================
# Comment Action Endpoints
# ============================================================================


@router.post("/{comment_id}/hide", response_model=HideCommentResponse)
async def hide_comment(
    comment_id: str,
    comment_repo: CommentRepository = Depends(get_comment_repository),
    container: Container = Depends(get_container),
):
    """
    Hide an Instagram comment (queues Celery task).

    Returns:
        HideCommentResponse with task ID or error
    """
    comment = await comment_repo.get_by_id(comment_id)

    if not comment:
        raise HTTPException(status_code=404, detail=f"Comment {comment_id} not found")

    if comment.is_hidden:
        return HideCommentResponse(
            status="already_hidden",
            message=f"Comment {comment_id} is already hidden",
            comment_id=comment_id,
            hidden_at=comment.hidden_at,
        )

    # Queue hide task using DI container
    task_queue = container.task_queue()
    task_id = task_queue.enqueue(
        "core.tasks.instagram_reply_tasks.hide_instagram_comment_task",
        comment_id,
    )

    logger.info(f"Hide task queued for comment {comment_id} (task_id={task_id})")

    return HideCommentResponse(
        status="queued",
        message=f"Hide task queued for comment {comment_id}",
        comment_id=comment_id,
        task_id=task_id,
    )


@router.post("/{comment_id}/unhide", response_model=UnhideCommentResponse)
async def unhide_comment(
    comment_id: str,
    use_case: HideCommentUseCase = Depends(get_hide_comment_use_case),
):
    """
    Unhide an Instagram comment (executes immediately using use case).

    This endpoint demonstrates the new DI pattern:
    - Dependencies injected via FastAPI Depends
    - Use case provided by DI container
    - All services injected through protocols (IInstagramService)

    Returns:
        UnhideCommentResponse with success/error status
    """
    # Use Clean Architecture with Dependency Injection
    result = await use_case.execute(comment_id, hide=False)

    if result["status"] == "error":
        raise HTTPException(
            status_code=500,
            detail=f"Failed to unhide comment: {result.get('reason', 'Unknown error')}",
        )

    if result["status"] == "not_hidden":
        return UnhideCommentResponse(
            status="not_hidden",
            message=f"Comment {comment_id} is not hidden",
            comment_id=comment_id,
        )

    logger.info(f"Successfully unhid comment {comment_id}")

    return UnhideCommentResponse(
        status="success",
        message=f"Comment {comment_id} unhidden successfully",
        comment_id=comment_id,
    )


@router.post("/{comment_id}/reply", response_model=SendReplyResponse)
async def send_manual_reply(
    comment_id: str,
    message: str = Query(..., min_length=1, max_length=500, description="Reply message"),
    comment_repo: CommentRepository = Depends(get_comment_repository),
    container: Container = Depends(get_container),
):
    """
    Send a manual reply to a comment (queues Celery task).

    Args:
        comment_id: Instagram comment ID
        message: Reply text (1-500 characters)

    Returns:
        SendReplyResponse with task ID or error
    """
    comment = await comment_repo.get_by_id(comment_id)

    if not comment:
        raise HTTPException(status_code=404, detail=f"Comment {comment_id} not found")

    # Queue reply task using DI container
    task_queue = container.task_queue()
    task_id = task_queue.enqueue(
        "core.tasks.instagram_reply_tasks.send_instagram_reply_task",
        comment_id,
        message,
    )

    logger.info(f"Manual reply task queued for comment {comment_id} (task_id={task_id})")

    return SendReplyResponse(
        status="queued",
        message=f"Reply task queued for comment {comment_id}",
        comment_id=comment_id,
        task_id=task_id,
        reply_text=message,
    )
