"""Helper functions for webhook processing."""

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from core.models.instagram_comment import InstagramComment
from core.repositories.comment import CommentRepository
from core.repositories.answer import AnswerRepository
from core.config import settings
from core.utils.time import now_db_utc

from .schemas import CommentValue

logger = logging.getLogger(__name__)


async def should_skip_comment(
    comment: CommentValue, session: AsyncSession
) -> tuple[bool, str]:
    """
    Determine if a comment should be skipped.

    Returns:
        (should_skip, reason) tuple
    """
    comment_id = comment.id

    # Check 1: Is this from our bot?
    if settings.instagram.bot_username:
        if comment.is_from_user(settings.instagram.bot_username):
            return True, f"Bot reply detected ({comment.from_.username})"

    # Check 2: Is this a reply to our bot's comment?
    if comment.is_reply():
        parent_id = comment.parent_id

        # Use repository to check if parent is our bot's reply
        answer_repo = AnswerRepository(session)
        parent_answer = await answer_repo.get_by_reply_id(parent_id)
        if parent_answer:
            return True, f"Reply to bot comment {parent_id}"

    # Check 3: Is this comment_id already our bot's reply?
    answer_repo = AnswerRepository(session)
    own_reply = await answer_repo.get_by_reply_id(comment_id)
    if own_reply:
        return True, "Own reply detected via reply_id"

    return False, ""


async def get_existing_comment(
    comment_id: str, session: AsyncSession
) -> Optional[InstagramComment]:
    """Get existing comment from database if it exists."""
    comment_repo = CommentRepository(session)
    return await comment_repo.get_by_id(comment_id)


def extract_comment_data(comment: CommentValue, entry_timestamp: int) -> dict:
    """Extract comment data for database insertion."""
    from datetime import datetime

    return {
        "id": comment.id,
        "media_id": comment.media.id,
        "user_id": comment.from_.id,
        "username": comment.from_.username,
        "text": comment.text,
        "created_at": datetime.fromtimestamp(entry_timestamp),
        "parent_id": comment.parent_id,
        "raw_data": comment.model_dump(),
    }
