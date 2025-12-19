"""Unit tests for YouTube Celery tasks."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, Dict

import pytest
from celery.exceptions import Retry

from core.tasks import youtube_tasks as tasks
from core.utils.task_helpers import _close_worker_event_loop, get_retry_delay


class DummyTask:
    """Lightweight bound Celery task surrogate."""

    def __init__(self, *, retries: int = 0, max_retries: int = 5):
        self.request = SimpleNamespace(id="task-yt", retries=retries)
        self.max_retries = max_retries
        self.retry_calls: list[dict[str, Any]] = []

    def retry(self, *args, **kwargs):
        self.retry_calls.append({"args": args, "kwargs": kwargs})
        raise Retry("retry requested")


class _DummyOAuthService:
    def __init__(self, tokens: Dict[str, Any] | None):
        self._tokens = tokens

    async def get_tokens(self, *_args, **_kwargs):
        return self._tokens


class _DummyUseCase:
    def __init__(self, result: Dict[str, Any]):
        self._result = result
        self.calls = 0

    async def execute(self, **_kwargs):
        self.calls += 1
        return self._result


class _DummyContainer:
    def __init__(self, tokens: Dict[str, Any] | None, result: Dict[str, Any]):
        self.oauth_service = _DummyOAuthService(tokens)
        self.use_case = _DummyUseCase(result)

    def oauth_token_service(self, *, session):
        return self.oauth_service

    def poll_youtube_comments_use_case(self, *, session):
        return self.use_case


def _patch_container(monkeypatch, container: _DummyContainer):
    monkeypatch.setattr(tasks, "get_container", lambda: container)

    @asynccontextmanager
    async def _session_ctx():
        yield SimpleNamespace()

    monkeypatch.setattr(tasks, "get_db_session", _session_ctx)


def _run_poll(task: DummyTask, *args, **kwargs):
    run_func = tasks.poll_youtube_comments_task.run.__func__
    try:
        return run_func(task, *args, **kwargs)
    finally:
        _close_worker_event_loop()


def test_poll_skips_when_missing_tokens(monkeypatch):
    container = _DummyContainer(tokens=None, result={"status": "success"})
    _patch_container(monkeypatch, container)
    task = DummyTask()

    result = _run_poll(task)

    assert result["status"] == "skipped"
    assert not task.retry_calls


def test_poll_retries_on_error(monkeypatch):
    container = _DummyContainer(tokens={"access_token": "a"}, result={"status": "error", "reason": "boom"})
    _patch_container(monkeypatch, container)
    task = DummyTask(retries=0)

    with pytest.raises(Retry):
        _run_poll(task)

    assert task.retry_calls
    delay = task.retry_calls[0]["kwargs"].get("countdown")
    assert delay == get_retry_delay(0)


def test_poll_no_retry_on_auth_error(monkeypatch):
    container = _DummyContainer(tokens={"access_token": "a"}, result={"status": "auth_error", "reason": "invalid"})
    _patch_container(monkeypatch, container)
    task = DummyTask()

    result = _run_poll(task)

    assert result["status"] == "auth_error"
    assert not task.retry_calls
