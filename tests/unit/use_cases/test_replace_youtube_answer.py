"""Unit tests for ReplaceYouTubeAnswerUseCase."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from core.repositories.answer import AnswerRepository
from core.repositories.comment import CommentRepository
from core.use_cases.replace_youtube_answer import ReplaceYouTubeAnswerUseCase


@pytest.mark.unit
@pytest.mark.use_case
class TestReplaceYouTubeAnswerUseCase:
    async def test_execute_updates_existing_reply(
        self,
        db_session,
        comment_factory,
        answer_factory,
    ):
        comment = await comment_factory(comment_id="yt_comment_1", platform="youtube")
        old_answer = await answer_factory(
            comment_id=comment.id,
            reply_id="reply-1",
            reply_sent=True,
        )

        yt_service = MagicMock()
        yt_service.update_comment = AsyncMock(return_value={"id": "reply-1"})
        yt_service.delete_comment = AsyncMock()
        yt_service.reply_to_comment = AsyncMock()

        use_case = ReplaceYouTubeAnswerUseCase(
            session=db_session,
            answer_repository_factory=AnswerRepository,
            comment_repository_factory=CommentRepository,
            youtube_service=yt_service,
        )

        new_answer = await use_case.execute(
            answer_id=old_answer.id,
            new_answer_text="Updated reply text",
        )

        assert new_answer.reply_id == "reply-1"
        yt_service.update_comment.assert_awaited_once_with(comment_id="reply-1", text="Updated reply text")
        yt_service.delete_comment.assert_not_awaited()
        yt_service.reply_to_comment.assert_not_awaited()
        await db_session.refresh(old_answer)
        assert old_answer.is_deleted is True
        assert old_answer.reply_status == "updated"

    async def test_execute_falls_back_to_delete_insert(
        self,
        db_session,
        comment_factory,
        answer_factory,
    ):
        comment = await comment_factory(comment_id="yt_comment_2", platform="youtube")
        old_answer = await answer_factory(
            comment_id=comment.id,
            reply_id="reply-old",
            reply_sent=True,
        )

        yt_service = MagicMock()
        yt_service.update_comment = AsyncMock(side_effect=RuntimeError("not supported"))
        yt_service.delete_comment = AsyncMock(return_value=None)
        yt_service.reply_to_comment = AsyncMock(return_value={"id": "reply-new"})

        use_case = ReplaceYouTubeAnswerUseCase(
            session=db_session,
            answer_repository_factory=AnswerRepository,
            comment_repository_factory=CommentRepository,
            youtube_service=yt_service,
        )

        new_answer = await use_case.execute(
            answer_id=old_answer.id,
            new_answer_text="Replacement reply",
        )

        assert new_answer.reply_id == "reply-new"
        yt_service.update_comment.assert_awaited_once()
        yt_service.delete_comment.assert_awaited_once_with("reply-old")
        yt_service.reply_to_comment.assert_awaited_once_with(parent_id=comment.id, text="Replacement reply")
        await db_session.refresh(old_answer)
        assert old_answer.is_deleted is True
