"""Unit tests for DeleteYouTubeCommentUseCase."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from core.use_cases.delete_youtube_comment import DeleteYouTubeCommentUseCase
from core.repositories.comment import CommentRepository


@pytest.mark.asyncio
async def test_delete_youtube_comment_success(db_session, comment_factory):
    comment = await comment_factory(comment_id="c-del", media_id="m1", platform="youtube")
    yt_service = MagicMock()
    yt_service.delete_comment = AsyncMock()

    use_case = DeleteYouTubeCommentUseCase(
        session=db_session,
        youtube_service=yt_service,
        comment_repository_factory=CommentRepository,
    )

    result = await use_case.execute(comment_id=comment.id)

    assert result["status"] == "success"
    yt_service.delete_comment.assert_awaited_once_with(comment.id)


@pytest.mark.asyncio
async def test_delete_youtube_comment_missing(db_session):
    yt_service = MagicMock()
    yt_service.delete_comment = AsyncMock()

    use_case = DeleteYouTubeCommentUseCase(
        session=db_session,
        youtube_service=yt_service,
        comment_repository_factory=CommentRepository,
    )

    result = await use_case.execute(comment_id="nope")

    assert result["status"] == "error"
    yt_service.delete_comment.assert_not_called()


@pytest.mark.asyncio
async def test_delete_youtube_comment_forbidden_with_string_status(db_session, comment_factory):
    comment = await comment_factory(comment_id="c-forbidden", media_id="m1", platform="youtube")

    class DummyForbidden(Exception):
        def __init__(self) -> None:
            super().__init__("Forbidden")
            self.status_code = "403"

    yt_service = MagicMock()
    yt_service.delete_comment = AsyncMock(side_effect=DummyForbidden())

    use_case = DeleteYouTubeCommentUseCase(
        session=db_session,
        youtube_service=yt_service,
        comment_repository_factory=CommentRepository,
    )

    result = await use_case.execute(comment_id=comment.id)

    assert result["status"] == "error"
    assert result["reason"] == "forbidden"
