"""
Conversation Management API

This module provides endpoints for managing conversation sessions and history.
"""

import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from core.models.db_helper import db_helper
from core.models.question_answer import QuestionAnswer, AnswerStatus
from core.models.instagram_comment import InstagramComment
from core.services.answer_service import QuestionAnswerService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["conversations"])

@router.get("/conversations")
async def list_conversations(
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(db_helper.scoped_session_dependency)
):
    """
    List all conversations with their metadata
    """
    try:
        # Get conversations with their answer counts
        result = await session.execute(
            select(
                QuestionAnswer.conversation_id,
                func.count(QuestionAnswer.id).label('answer_count'),
                func.max(QuestionAnswer.processing_completed_at).label('last_activity')
            )
            .where(QuestionAnswer.conversation_id.isnot(None))
            .group_by(QuestionAnswer.conversation_id)
            .order_by(func.max(QuestionAnswer.processing_completed_at).desc())
            .limit(limit)
            .offset(offset)
        )
        
        conversations = []
        for row in result:
            conversations.append({
                "conversation_id": row.conversation_id,
                "answer_count": row.answer_count,
                "last_activity": row.last_activity
            })
        
        return {
            "conversations": conversations,
            "total": len(conversations),
            "limit": limit,
            "offset": offset
        }
        
    except Exception as e:
        logger.error(f"Error listing conversations: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/conversations/{conversation_id}")
async def get_conversation_details(
    conversation_id: str,
    session: AsyncSession = Depends(db_helper.scoped_session_dependency)
):
    """
    Get details about a specific conversation
    """
    try:
        # Get all answers for this conversation
        result = await session.execute(
            select(QuestionAnswer)
            .where(QuestionAnswer.conversation_id == conversation_id)
            .order_by(QuestionAnswer.processing_completed_at)
        )
        
        answers = result.scalars().all()
        
        if not answers:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Get conversation history from AnswerService
        answer_service = QuestionAnswerService()
        history = answer_service.get_conversation_history(conversation_id)
        
        return {
            "conversation_id": conversation_id,
            "answer_count": len(answers),
            "answers": [
                {
                    "comment_id": answer.comment_id,
                    "answer": answer.answer,
                    "confidence": answer.answer_confidence,
                    "quality_score": answer.answer_quality_score,
                    "processing_status": answer.processing_status.value,
                    "completed_at": answer.processing_completed_at,
                    "meta_data": answer.meta_data
                }
                for answer in answers
            ],
            "session_history": history
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting conversation details: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.delete("/conversations/{conversation_id}")
async def clear_conversation(
    conversation_id: str,
    session: AsyncSession = Depends(db_helper.scoped_session_dependency)
):
    """
    Clear the conversation history for a specific conversation
    """
    try:
        # Check if conversation exists
        result = await session.execute(
            select(QuestionAnswer)
            .where(QuestionAnswer.conversation_id == conversation_id)
            .limit(1)
        )
        
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Clear the conversation using AnswerService
        answer_service = QuestionAnswerService()
        success = answer_service.clear_conversation(conversation_id)
        
        if success:
            return {
                "message": f"Conversation {conversation_id} cleared successfully",
                "conversation_id": conversation_id
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to clear conversation")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clearing conversation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/conversations/{conversation_id}/history")
async def get_conversation_history(
    conversation_id: str
):
    """
    Get the raw conversation history from SQLiteSession
    """
    try:
        answer_service = QuestionAnswerService()
        history = answer_service.get_conversation_history(conversation_id)
        
        return {
            "conversation_id": conversation_id,
            "history": history
        }
        
    except Exception as e:
        logger.error(f"Error getting conversation history: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/conversations/{conversation_id}/session-info")
async def get_session_info(
    conversation_id: str
):
    """
    Get session information for a specific conversation
    """
    try:
        answer_service = QuestionAnswerService()
        session_info = answer_service.get_session_info(conversation_id)
        
        return session_info
        
    except Exception as e:
        logger.error(f"Error getting session info: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/comments/{comment_id}/thread")
async def get_comment_thread(
    comment_id: str,
    session: AsyncSession = Depends(db_helper.scoped_session_dependency)
):
    """
    Get the comment thread (parent comment and all replies)
    """
    try:
        # Get the main comment
        result = await session.execute(
            select(InstagramComment)
            .where(InstagramComment.id == comment_id)
        )
        main_comment = result.scalar_one_or_none()
        
        if not main_comment:
            raise HTTPException(status_code=404, detail="Comment not found")
        
        # Determine the root comment (if this is a reply, find the parent)
        root_comment_id = comment_id
        if main_comment.parent_id:
            root_comment_id = main_comment.parent_id
            # Get the root comment
            result = await session.execute(
                select(InstagramComment)
                .where(InstagramComment.id == root_comment_id)
            )
            root_comment = result.scalar_one_or_none()
            if not root_comment:
                raise HTTPException(status_code=404, detail="Root comment not found")
        else:
            root_comment = main_comment
        
        # Get all replies to the root comment
        result = await session.execute(
            select(InstagramComment)
            .where(InstagramComment.parent_id == root_comment_id)
            .order_by(InstagramComment.created_at)
        )
        replies = result.scalars().all()
        
        return {
            "root_comment": {
                "id": root_comment.id,
                "text": root_comment.text,
                "username": root_comment.username,
                "created_at": root_comment.created_at,
                "parent_id": root_comment.parent_id
            },
            "replies": [
                {
                    "id": reply.id,
                    "text": reply.text,
                    "username": reply.username,
                    "created_at": reply.created_at,
                    "parent_id": reply.parent_id
                }
                for reply in replies
            ],
            "thread_size": len(replies) + 1
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting comment thread: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
