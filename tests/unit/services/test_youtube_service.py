"""Unit tests for YouTubeService core behaviors."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services import youtube_service
from core.services.youtube_service import MissingYouTubeAuth, YouTubeService


@pytest.mark.asyncio
async def test_build_credentials_raises_without_tokens(monkeypatch):
    """Missing stored tokens should raise a clear auth error."""
    service = YouTubeService(token_service_factory=None, session_factory=None, channel_id=None)
    service._account_id = None
    monkeypatch.setattr(youtube_service, "_ensure_google_imports", lambda: None)
    monkeypatch.setattr(service, "_load_tokens", AsyncMock(return_value=None))

    with pytest.raises(MissingYouTubeAuth):
        await service._build_credentials()


class _DummyCredentials:
    def __init__(self, token, refresh_token=None, token_uri=None, client_id=None, client_secret=None, scopes=None, expiry=None):
        self.token = token
        self.refresh_token = refresh_token
        self.token_uri = token_uri
        self.client_id = client_id
        self.client_secret = client_secret
        self.scopes = scopes
        self.expiry = expiry
        self.valid = True


@pytest.mark.asyncio
async def test_build_credentials_uses_stored_tokens(monkeypatch):
    """Stored tokens should produce credentials and cache account_id."""
    service = YouTubeService(token_service_factory=None, session_factory=None, channel_id=None)
    service._account_id = None
    monkeypatch.setattr(youtube_service, "_ensure_google_imports", lambda: None)
    monkeypatch.setattr(youtube_service, "Credentials", _DummyCredentials)
    tokens = {
        "access_token": "access",
        "refresh_token": "refresh",
        "account_id": "chan-1",
        "expires_at": None,
    }
    monkeypatch.setattr(service, "_load_tokens", AsyncMock(return_value=tokens))

    creds = await service._build_credentials()

    assert isinstance(creds, _DummyCredentials)
    assert service._account_id == "chan-1"
    assert creds.token == "access"
    assert creds.refresh_token == "refresh"


@pytest.mark.asyncio
async def test_list_channel_videos_uses_uploads_playlist(monkeypatch):
    service = YouTubeService(token_service_factory=None, session_factory=None)
    monkeypatch.setattr(youtube_service, "_ensure_google_imports", lambda: None)
    monkeypatch.setattr(service, "_get_youtube", AsyncMock(return_value=MagicMock()))
    monkeypatch.setattr(service, "_get_uploads_playlist_id", AsyncMock(return_value="uploads123"))
    execute_mock = AsyncMock(return_value={"items": []})
    monkeypatch.setattr(service, "_execute", execute_mock)

    result = await service.list_channel_videos()

    assert result == {"items": []}
    service._get_uploads_playlist_id.assert_awaited_once_with(channel_id=None)
    execute_mock.assert_awaited_once()


class _FakeRequest:
    def __init__(self, response):
        self._response = response

    def execute(self):
        return self._response


class _FakeComments:
    def __init__(self, response):
        self._response = response
        self.last_body = None

    def insert(self, *, part, body):
        assert part == "snippet"
        self.last_body = body
        return _FakeRequest(self._response)

    def delete(self, *, id):
        return _FakeRequest({"deleted": id})

    def update(self, *, part, body):
        assert part == "snippet"
        self.last_body = body
        return _FakeRequest(self._response)


class _FakeYouTube:
    def __init__(self, comments: _FakeComments):
        self._comments = comments

    def comments(self):
        return self._comments


@pytest.mark.asyncio
async def test_reply_to_comment_executes_with_body(monkeypatch):
    """Ensure reply call flows through _execute and preserves body."""
    comments = _FakeComments({"id": "reply-1"})
    service = YouTubeService(token_service_factory=None, session_factory=None)
    monkeypatch.setattr(youtube_service, "_ensure_google_imports", lambda: None)
    monkeypatch.setattr(service, "_get_youtube", AsyncMock(return_value=_FakeYouTube(comments)))

    async def fake_execute(call):
        return call()

    monkeypatch.setattr(service, "_execute", AsyncMock(side_effect=fake_execute))

    result = await service.reply_to_comment(parent_id="c1", text="hi there")

    assert result["id"] == "reply-1"
    assert comments.last_body == {"snippet": {"parentId": "c1", "textOriginal": "hi there"}}
    service._execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_comment_executes_with_body(monkeypatch):
    """Ensure update call flows through _execute and preserves body."""
    comments = _FakeComments({"id": "reply-1"})
    service = YouTubeService(token_service_factory=None, session_factory=None)
    monkeypatch.setattr(youtube_service, "_ensure_google_imports", lambda: None)
    monkeypatch.setattr(service, "_get_youtube", AsyncMock(return_value=_FakeYouTube(comments)))

    async def fake_execute(call):
        return call()

    monkeypatch.setattr(service, "_execute", AsyncMock(side_effect=fake_execute))

    result = await service.update_comment(comment_id="c1", text="updated text")

    assert result["id"] == "reply-1"
    assert comments.last_body == {"id": "c1", "snippet": {"textOriginal": "updated text"}}
    service._execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_comment_executes(monkeypatch):
    comments = _FakeComments({"deleted": "c-123"})
    service = YouTubeService(token_service_factory=None, session_factory=None)
    monkeypatch.setattr(youtube_service, "_ensure_google_imports", lambda: None)
    monkeypatch.setattr(service, "_get_youtube", AsyncMock(return_value=_FakeYouTube(comments)))

    async def fake_execute(call):
        return call()

    exec_mock = AsyncMock(side_effect=fake_execute)
    monkeypatch.setattr(service, "_execute", exec_mock)

    await service.delete_comment(comment_id="c-123")

    exec_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_account_id_uses_cached_tokens(monkeypatch):
    service = YouTubeService(token_service_factory=None, session_factory=None, channel_id=None)
    service._account_id = None
    monkeypatch.setattr(service, "_load_tokens", AsyncMock(return_value={"account_id": "cached-id"}))
    monkeypatch.setattr(service, "_get_youtube", AsyncMock())

    account_id = await service.get_account_id()

    assert account_id == "cached-id"
    service._get_youtube.assert_not_called()
