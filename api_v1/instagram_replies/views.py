import datetime
from typing import List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.models import QuestionAnswer, InstagramComment, AnswerStatus
from core.models.db_helper import db_helper
from core.tasks.instagram_reply_tasks import send_instagram_reply_async

router = APIRouter(tags=["instagram-replies"])

@router.post("/send/{comment_id}")
async def send_reply_manually(
    comment_id: str,
    session: AsyncSession = Depends(db_helper.scoped_session_dependency)
):
    """
    Manually send an Instagram reply for a specific comment.
    """
    # Check if comment exists and has a completed answer
    result = await session.execute(
        select(InstagramComment)
        .options(selectinload(InstagramComment.question_answer))
        .where(InstagramComment.id == comment_id)
    )
    comment = result.scalar_one_or_none()

    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    if not comment.question_answer:
        raise HTTPException(status_code=400, detail="Comment has no answer")

    if comment.question_answer.processing_status != AnswerStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Answer is not completed yet")

    if not comment.question_answer.answer:
        raise HTTPException(status_code=400, detail="No answer text available")

    # Run the reply sending directly
    result = await send_instagram_reply_async(comment_id, comment.question_answer.answer)

    return {"status": "completed", "comment_id": comment_id, "result": result}

@router.get("/status/{comment_id}")
async def get_reply_status(
    comment_id: str,
    session: AsyncSession = Depends(db_helper.scoped_session_dependency)
):
    """
    Get the Instagram reply status for a specific comment.
    """
    stmt = select(QuestionAnswer).where(QuestionAnswer.comment_id == comment_id)
    result = await session.execute(stmt)
    answer = result.scalar_one_or_none()

    if not answer:
        raise HTTPException(status_code=404, detail="Answer not found for this comment")

    return {
        "comment_id": answer.comment_id,
        "reply_sent": answer.reply_sent,
        "reply_sent_at": answer.reply_sent_at,
        "reply_status": answer.reply_status,
        "reply_error": answer.reply_error,
        "answer_available": answer.answer is not None,
        "answer_status": answer.processing_status.value
    }

@router.get("/stats")
async def get_reply_stats(session: AsyncSession = Depends(db_helper.scoped_session_dependency)):
    """
    Get statistics about Instagram replies.
    """
    # Count replies by status
    status_counts_query = await session.execute(
        select(
            QuestionAnswer.reply_status,
            func.count(QuestionAnswer.id)
        ).where(
            QuestionAnswer.answer.isnot(None)
        ).group_by(QuestionAnswer.reply_status)
    )
    status_counts = {status: count for status, count in status_counts_query.all() if status}

    # Count total replies sent
    total_sent_query = await session.execute(
        select(func.count(QuestionAnswer.id)).where(QuestionAnswer.reply_sent == True)
    )
    total_sent = total_sent_query.scalar() or 0

    # Count pending replies
    pending_query = await session.execute(
        select(func.count(QuestionAnswer.id)).where(
            and_(
                QuestionAnswer.processing_status == AnswerStatus.COMPLETED,
                QuestionAnswer.answer.isnot(None),
                QuestionAnswer.reply_sent == False
            )
        )
    )
    pending_count = pending_query.scalar() or 0

    # Count total with answers
    total_with_answers_query = await session.execute(
        select(func.count(QuestionAnswer.id)).where(QuestionAnswer.answer.isnot(None))
    )
    total_with_answers = total_with_answers_query.scalar() or 0

    return {
        "total_replies_sent": total_sent,
        "pending_replies": pending_count,
        "status_breakdown": status_counts,
        "total_with_answers": total_with_answers
    }

@router.get("/pending")
async def get_pending_replies(
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(db_helper.scoped_session_dependency)
):
    """
    Get a list of comments with completed answers that haven't been replied to yet.
    """
    stmt = select(QuestionAnswer).where(
        and_(
            QuestionAnswer.processing_status == AnswerStatus.COMPLETED,
            QuestionAnswer.answer.isnot(None),
            QuestionAnswer.reply_sent == False
        )
    ).offset(offset).limit(limit)

    result = await session.execute(stmt)
    pending_answers = result.scalars().all()

    return [
        {
            "comment_id": answer.comment_id,
            "answer": answer.answer,
            "answer_confidence": answer.answer_confidence,
            "answer_quality_score": answer.answer_quality_score,
            "processing_completed_at": answer.processing_completed_at,
        }
        for answer in pending_answers
    ]

@router.post("/process-pending")
async def process_pending_replies(session: AsyncSession = Depends(db_helper.scoped_session_dependency)):
    """
    Process all pending replies manually.
    """
    from core.tasks.instagram_reply_tasks import process_pending_replies_async
    
    result = await process_pending_replies_async()
    return result

@router.get("/validate-token")
async def validate_instagram_token():
    """
    Validate the Instagram access token and return token information.
    """
    try:
        from core.services.instagram_service import InstagramGraphAPIService
        instagram_service = InstagramGraphAPIService()
        validation_result = await instagram_service.validate_token()
        
        if validation_result["success"]:
            return {
                "status": "success",
                "message": "Instagram access token is valid",
                "token_info": validation_result["token_info"]
            }
        else:
            return {
                "status": "error",
                "message": "Instagram access token validation failed",
                "error": validation_result["error"]
            }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to validate Instagram token: {str(e)}"
        }

@router.get("/page-info")
async def get_instagram_page_info():
    """
    Get Instagram page information using the access token.
    """
    try:
        from core.services.instagram_service import InstagramGraphAPIService
        instagram_service = InstagramGraphAPIService()
        page_info_result = await instagram_service.get_page_info()
        
        if page_info_result["success"]:
            return {
                "status": "success",
                "message": "Successfully retrieved Instagram page info",
                "page_info": page_info_result["page_info"]
            }
        else:
            return {
                "status": "error",
                "message": "Failed to get Instagram page info",
                "error": page_info_result["error"]
            }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to get Instagram page info: {str(e)}"
        }
