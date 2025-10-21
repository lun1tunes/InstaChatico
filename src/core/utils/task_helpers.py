"""Task utility helpers for Celery async tasks."""

import asyncio
import logging
from contextlib import asynccontextmanager
from functools import wraps
from typing import Callable, Optional

from ..container import get_container

logger = logging.getLogger(__name__)


def _get_worker_event_loop() -> asyncio.AbstractEventLoop:
    """
    Provide a stable event loop for Celery worker processes.

    Celery runs tasks synchronously inside worker processes. Creating a fresh
    loop per task breaks async drivers like asyncpg (connections are bound to
    the loop they were created on). We lazily create a single loop per process
    and reuse it for every task to keep futures on the correct loop.
    """
    loop = getattr(_get_worker_event_loop, "_loop", None)
    if loop is None:
        loop = asyncio.new_event_loop()
        _get_worker_event_loop._loop = loop  # type: ignore[attr-defined]
    return loop


def _close_worker_event_loop() -> None:
    """Close the cached worker event loop (used in tests to avoid warnings)."""
    loop: Optional[asyncio.AbstractEventLoop] = getattr(_get_worker_event_loop, "_loop", None)  # type: ignore[attr-defined]
    if loop is not None and not loop.is_closed():
        loop.close()
    if hasattr(_get_worker_event_loop, "_loop"):
        delattr(_get_worker_event_loop, "_loop")


def async_task(celery_task_func: Callable):
    """Decorator for Celery tasks that run async functions without loop churn."""

    @wraps(celery_task_func)
    def wrapper(*args, **kwargs):
        loop = _get_worker_event_loop()
        try:
            current = asyncio.get_running_loop()
        except RuntimeError:
            current = None

        if current is not loop:
            policy_loop = None
            if current is None:
                try:
                    policy_loop = asyncio.get_event_loop_policy().get_event_loop()
                except RuntimeError:
                    policy_loop = None

            if policy_loop is not loop:
                asyncio.set_event_loop(loop)
        return loop.run_until_complete(celery_task_func(*args, **kwargs))

    return wrapper


@asynccontextmanager
async def get_db_session():
    """Context manager for database session using container-managed session factory."""
    container = get_container()
    session_factory = container.db_session_factory()

    async with session_factory() as session:
        yield session


def retry_with_backoff(task_instance, exc: Exception, max_retries: int = 3):
    """Handle retry logic with exponential backoff."""
    if task_instance and task_instance.request.retries < max_retries:
        retry_countdown = 2**task_instance.request.retries * 60
        raise task_instance.retry(countdown=retry_countdown, exc=exc)
    return {"status": "error", "reason": str(exc)}
