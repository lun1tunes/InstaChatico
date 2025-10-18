"""Task utility helpers for Celery async tasks."""

import asyncio
import logging
from contextlib import asynccontextmanager
from functools import wraps
from typing import Callable

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


def async_task(celery_task_func: Callable):
    """Decorator for Celery tasks that run async functions without loop churn."""

    @wraps(celery_task_func)
    def wrapper(*args, **kwargs):
        loop = _get_worker_event_loop()
        if asyncio.get_event_loop_policy().get_event_loop() is not loop:
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
