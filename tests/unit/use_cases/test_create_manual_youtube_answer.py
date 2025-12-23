"""Unit tests for CreateManualYouTubeAnswerUseCase."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from core.use_cases.create_manual_youtube_answer import CreateManualYouTubeAnswerUseCase
from core.repositories.answer import AnswerRepository
from core.repositories.comment import CommentRepository
from core.models.question_answer import QuestionAnswer, AnswerStatus


@pytest.mark.unit
@pytest.mark.use_case
class TestCreateManualYouTubeAnswerUseCase:
    async def test_execute_creates_reply_and_injects_conversation(
        self,
        db_session,
        comment_factory,
    ):
        comment = await comment_factory(
            comment_id="yt_comment_1",
            text="Do you ship internationally?",
            username="customer1",
            platform="youtube",
            conversation_id=None,
        )

        yt_service = MagicMock()
        yt_service.get_account_id = AsyncMock(return_value="channel-1")
        yt_service.reply_to_comment = AsyncMock(return_value={"id": "yt-reply-1"})

        session_mock = AsyncMock()
        session_mock.add_items = AsyncMock()

        session_service = MagicMock()
        session_service.get_session.return_value = session_mock

        use_case = CreateManualYouTubeAnswerUseCase(
            session=db_session,
            comment_repository_factory=lambda session: CommentRepository(session),
            answer_repository_factory=lambda session: AnswerRepository(session),
            youtube_service=yt_service,
            replace_answer_use_case_factory=lambda session: MagicMock(),
            session_service=session_service,
        )

        result = await use_case.execute(
            comment_id=comment.id,
            answer_text="Yes, worldwide shipping is available.",
        )

        assert result.answer == "Yes, worldwide shipping is available."
        assert result.reply_id == "yt-reply-1"
        yt_service.reply_to_comment.assert_awaited_once_with(parent_id=comment.id, text="Yes, worldwide shipping is available.")
        session_service.get_session.assert_called_once_with("first_question_comment_yt_comment_1")
        session_mock.add_items.assert_awaited_once()

    async def test_execute_existing_answer_uses_replace(
        self,
        db_session,
        comment_factory,
        answer_factory,
    ):
        comment = await comment_factory(
            comment_id="yt_comment_2",
            text="Can I cancel my order?",
            username="customer2",
            platform="youtube",
            conversation_id=None,
        )
        await answer_factory(comment_id=comment.id, answer_text="Old answer")

        mock_replace_use_case = MagicMock()
        mock_replace_use_case.execute = AsyncMock(
            return_value=QuestionAnswer(
                comment_id=comment.id,
                answer="Updated answer",
                processing_status=AnswerStatus.COMPLETED,
            )
        )

        yt_service = MagicMock()
        yt_service.reply_to_comment = AsyncMock()

        session_mock = AsyncMock()
        session_mock.add_items = AsyncMock()

        session_service = MagicMock()
        session_service.get_session.return_value = session_mock

        use_case = CreateManualYouTubeAnswerUseCase(
            session=db_session,
            comment_repository_factory=lambda session: CommentRepository(session),
            answer_repository_factory=lambda session: AnswerRepository(session),
            youtube_service=yt_service,
            replace_answer_use_case_factory=lambda session: mock_replace_use_case,
            session_service=session_service,
        )

        result = await use_case.execute(comment_id=comment.id, answer_text="You can cancel within 2 hours.")

        assert result is mock_replace_use_case.execute.return_value
        mock_replace_use_case.execute.assert_awaited_once()
        yt_service.reply_to_comment.assert_not_awaited()
        session_service.get_session.assert_called_once_with("first_question_comment_yt_comment_2")
        session_mock.add_items.assert_awaited_once()
