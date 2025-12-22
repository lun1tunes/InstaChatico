"""Unit tests for SendYouTubeReplyUseCase."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from core.use_cases.send_youtube_reply import SendYouTubeReplyUseCase
from core.repositories.comment import CommentRepository
from core.repositories.answer import AnswerRepository


@pytest.mark.asyncio
async def test_send_youtube_reply_success(db_session, comment_factory, answer_factory):
    comment = await comment_factory(comment_id="c1", media_id="m1", platform="youtube", parent_id=None)
    await answer_factory(comment_id=comment.id, answer="hi there")

    yt_service = MagicMock()
    yt_service.reply_to_comment = AsyncMock(return_value={"id": "r1"})
    yt_service.get_account_id = AsyncMock(return_value="channel-1")

    use_case = SendYouTubeReplyUseCase(
        session=db_session,
        youtube_service=yt_service,
        comment_repository_factory=CommentRepository,
        answer_repository_factory=AnswerRepository,
    )

    result = await use_case.execute(comment_id=comment.id, reply_text="hi there", use_generated_answer=False)

    assert result["status"] == "success"
    assert result["reply_id"] == "r1"
    yt_service.reply_to_comment.assert_awaited_once_with(parent_id=comment.id, text="hi there")


@pytest.mark.asyncio
async def test_send_youtube_reply_skips_own_comment(db_session, comment_factory):
    raw_data = {"snippet": {"authorChannelId": {"value": "channel-1"}}}
    comment = await comment_factory(comment_id="c2", media_id="m2", platform="youtube", raw_data=raw_data)

    yt_service = MagicMock()
    yt_service.get_account_id = AsyncMock(return_value="channel-1")

    use_case = SendYouTubeReplyUseCase(
        session=db_session,
        youtube_service=yt_service,
        comment_repository_factory=CommentRepository,
        answer_repository_factory=AnswerRepository,
    )

    result = await use_case.execute(comment_id=comment.id, reply_text="custom", use_generated_answer=False)

    assert result["status"] == "skipped"
    assert result["reason"] == "own_comment"
    yt_service.get_account_id.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_youtube_reply_replies_to_thread_parent_for_reply_comment(db_session, comment_factory):
    """
    YouTube replies are attached to the top-level comment in the thread.
    If the target comment is a reply, we must post under its parent_id.
    """
    comment = await comment_factory(comment_id="reply-1", media_id="m3", platform="youtube", parent_id="top-1")

    yt_service = MagicMock()
    yt_service.reply_to_comment = AsyncMock(return_value={"id": "r2"})
    yt_service.get_account_id = AsyncMock(return_value="channel-1")

    use_case = SendYouTubeReplyUseCase(
        session=db_session,
        youtube_service=yt_service,
        comment_repository_factory=CommentRepository,
        answer_repository_factory=AnswerRepository,
    )

    result = await use_case.execute(comment_id=comment.id, reply_text="hello", use_generated_answer=False)

    assert result["status"] == "success"
    yt_service.reply_to_comment.assert_awaited_once_with(parent_id="top-1", text="hello")


@pytest.mark.asyncio
async def test_send_youtube_reply_skips_when_already_sent(db_session, comment_factory, answer_factory):
    comment = await comment_factory(comment_id="c3", media_id="m4", platform="youtube", parent_id=None)
    await answer_factory(comment_id=comment.id, reply_id="r-existing", reply_sent=True)

    yt_service = MagicMock()
    yt_service.reply_to_comment = AsyncMock(return_value={"id": "r-new"})
    yt_service.get_account_id = AsyncMock(return_value="channel-1")

    use_case = SendYouTubeReplyUseCase(
        session=db_session,
        youtube_service=yt_service,
        comment_repository_factory=CommentRepository,
        answer_repository_factory=AnswerRepository,
    )

    result = await use_case.execute(comment_id=comment.id, reply_text="hello", use_generated_answer=False)

    assert result["status"] == "skipped"
    assert result["reason"] == "reply_already_sent"
    yt_service.reply_to_comment.assert_not_awaited()
