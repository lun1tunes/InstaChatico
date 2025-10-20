"""Unit tests for classification Celery tasks."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, List, Optional
from unittest.mock import AsyncMock

import pytest
from celery.exceptions import Retry

from core.tasks import classification_tasks as tasks
from core.utils.task_helpers import _close_worker_event_loop


class DummyTask:
    """Lightweight bound Celery task surrogate."""

    def __init__(self, *, retries: int = 0, max_retries: int = 3):
        self.request = SimpleNamespace(id="task-1", retries=retries)
        self.max_retries = max_retries
        self.retry_calls: List[dict[str, Any]] = []

    def retry(self, *args, **kwargs):
        self.retry_calls.append({"args": args, "kwargs": kwargs})
        raise Retry("retry requested")


class DummyQueue:
    """Captures enqueued tasks for assertions."""

    def __init__(self, *, raise_error: Optional[Exception] = None):
        self.calls: List[tuple[Any, ...]] = []
        self.raise_error = raise_error

    def enqueue(self, *args):
        if self.raise_error:
            raise self.raise_error
        self.calls.append(args)
        return f"task-{len(self.calls)}"


@dataclass
class DummyContainer:
    classify_use_case: Any
    queue: DummyQueue

    def __post_init__(self):
        self.sessions: List[Any] = []

    def classify_comment_use_case(self, *, session):
        self.sessions.append(session)
        return self.classify_use_case

    def task_queue(self):
        return self.queue


def _patch_common(monkeypatch, container: DummyContainer, session_obj: Any):
    monkeypatch.setattr(tasks, "get_container", lambda: container)

    @asynccontextmanager
    async def _session_ctx():
        yield session_obj

    monkeypatch.setattr(tasks, "get_db_session", _session_ctx)


def _run_classify_task(task: DummyTask, *args, **kwargs):
    run_func = tasks.classify_comment_task.run.__func__
    try:
        return run_func(task, *args, **kwargs)
    finally:
        _close_worker_event_loop()


def _run_retry_wrapper(*args, **kwargs):
    run_attr = getattr(tasks.retry_failed_classifications, "run", None)
    if run_attr is None:
        run_func = tasks.retry_failed_classifications
    else:
        run_func = run_attr.__func__ if hasattr(run_attr, "__func__") else run_attr
    try:
        return run_func(*args, **kwargs)
    finally:
        _close_worker_event_loop()


def _make_use_case(result=None, *, side_effect=None):
    execute = AsyncMock(return_value=result)
    if side_effect is not None:
        execute.side_effect = side_effect
    return SimpleNamespace(execute=execute)


def test_classify_comment_success_question(monkeypatch):
    queue = DummyQueue()
    use_case = _make_use_case(
        {
            "status": "success",
            "comment_id": "c1",
            "classification": "Question / Inquiry",
            "confidence": 0.92,
        }
    )
    container = DummyContainer(classify_use_case=use_case, queue=queue)
    session = object()
    _patch_common(monkeypatch, container, session)

    task = DummyTask()
    result = _run_classify_task(task, "c1")

    assert result["status"] == "success"
    use_case.execute.assert_awaited_once_with("c1", retry_count=0)
    assert queue.calls == [("core.tasks.answer_tasks.generate_answer_task", "c1")]


def test_classify_comment_success_urgent(monkeypatch):
    queue = DummyQueue()
    use_case = _make_use_case(
        {"status": "success", "comment_id": "c1", "classification": "Urgent Issue / Complaint"}
    )
    container = DummyContainer(classify_use_case=use_case, queue=queue)
    session = object()
    _patch_common(monkeypatch, container, session)

    task = DummyTask()
    result = _run_classify_task(task, "c1")

    assert result["status"] == "success"
    assert queue.calls == [
        ("core.tasks.instagram_reply_tasks.hide_instagram_comment_task", "c1"),
        ("core.tasks.telegram_tasks.send_telegram_notification_task", "c1"),
    ]


def test_classify_comment_success_toxic(monkeypatch):
    queue = DummyQueue()
    use_case = _make_use_case(
        {"status": "success", "comment_id": "c5", "classification": "toxic / abusive"}
    )
    container = DummyContainer(classify_use_case=use_case, queue=queue)
    session = object()
    _patch_common(monkeypatch, container, session)

    task = DummyTask()
    result = _run_classify_task(task, "c5")

    assert result["status"] == "success"
    assert queue.calls == [("core.tasks.instagram_reply_tasks.hide_instagram_comment_task", "c5")]


def test_classify_comment_success_handles_enqueue_errors(monkeypatch):
    queue = DummyQueue(raise_error=ValueError("queue down"))
    use_case = _make_use_case(
        {"status": "success", "comment_id": "c9", "classification": "question / inquiry"}
    )
    container = DummyContainer(classify_use_case=use_case, queue=queue)
    session = object()
    _patch_common(monkeypatch, container, session)

    task = DummyTask()
    result = _run_classify_task(task, "c9")

    # Even with enqueue failures the task should still return success.
    assert result["status"] == "success"


def test_classify_comment_retry(monkeypatch):
    queue = DummyQueue()
    use_case = _make_use_case({"status": "retry", "reason": "rate_limited"})
    container = DummyContainer(classify_use_case=use_case, queue=queue)
    session = object()
    _patch_common(monkeypatch, container, session)

    task = DummyTask(retries=1, max_retries=3)
    with pytest.raises(Retry):
        _run_classify_task(task, "c1")

    assert task.retry_calls[0]["kwargs"]["countdown"] == 10


def test_classify_comment_retry_limit(monkeypatch):
    queue = DummyQueue()
    retry_result = {"status": "retry", "reason": "still waiting"}
    use_case = _make_use_case(retry_result)
    container = DummyContainer(classify_use_case=use_case, queue=queue)
    session = object()
    _patch_common(monkeypatch, container, session)

    task = DummyTask(retries=3, max_retries=3)
    result = _run_classify_task(task, "c1")

    assert result is retry_result
    assert task.retry_calls == []


def test_classify_comment_error(monkeypatch):
    queue = DummyQueue()
    use_case = _make_use_case({"status": "error", "reason": "missing data"})
    container = DummyContainer(classify_use_case=use_case, queue=queue)
    session = object()
    _patch_common(monkeypatch, container, session)

    task = DummyTask()
    result = _run_classify_task(task, "c1")

    assert result["status"] == "error"


def test_retry_failed_classifications_wrapper(monkeypatch):
    async_mock = AsyncMock(return_value={"retried_count": 1})
    monkeypatch.setattr(tasks, "retry_failed_classifications_async", async_mock)

    result = _run_retry_wrapper()

    assert result == {"retried_count": 1}
    async_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_retry_failed_classifications_async(monkeypatch):
    fake_items = [SimpleNamespace(comment_id="c1"), SimpleNamespace(comment_id="c2")]
    queue = DummyQueue()
    container = SimpleNamespace(task_queue=lambda: queue)

    class FakeRepository:
        def __init__(self, session):
            self.session = session

        async def get_pending_retries(self):
            return fake_items

    @asynccontextmanager
    async def _session_ctx():
        yield object()

    monkeypatch.setattr(tasks, "get_container", lambda: container)
    monkeypatch.setattr(tasks, "get_db_session", _session_ctx)
    monkeypatch.setattr("core.repositories.classification.ClassificationRepository", FakeRepository, raising=False)

    result = await tasks.retry_failed_classifications_async()

    assert result == {"retried_count": 2}
    assert queue.calls == [
        ("core.tasks.classification_tasks.classify_comment_task", "c1"),
        ("core.tasks.classification_tasks.classify_comment_task", "c2"),
    ]


@pytest.mark.asyncio
async def test_retry_failed_classifications_async_handles_errors(monkeypatch):
    queue = DummyQueue(raise_error=RuntimeError("redis down"))
    container = SimpleNamespace(task_queue=lambda: queue)

    class FakeRepository:
        def __init__(self, session):
            self.session = session

        async def get_pending_retries(self):
            return [SimpleNamespace(comment_id="c1")]

    @asynccontextmanager
    async def _session_ctx():
        yield object()

    monkeypatch.setattr(tasks, "get_container", lambda: container)
    monkeypatch.setattr(tasks, "get_db_session", _session_ctx)
    monkeypatch.setattr("core.repositories.classification.ClassificationRepository", FakeRepository, raising=False)

    result = await tasks.retry_failed_classifications_async()

    assert result["error"] == "redis down"
