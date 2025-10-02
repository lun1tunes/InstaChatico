"""Task utility helpers for Celery async tasks."""

import asyncio
import logging
from contextlib import asynccontextmanager
from functools import wraps
from typing import Callable

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from ..config import settings

logger = logging.getLogger(__name__)


def async_task(celery_task_func):
    """Decorator for Celery tasks that run async functions with event loop management."""
    @wraps(celery_task_func)
    def wrapper(*args, **kwargs):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(celery_task_func(*args, **kwargs))
        finally:
            loop.close()
    return wrapper


@asynccontextmanager
async def get_db_session():
    """Context manager for database session with automatic cleanup."""
    engine = create_async_engine(settings.db.url, echo=settings.db.echo)
    session_factory = async_sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )

    async with session_factory() as session:
        try:
            yield session
        finally:
            await engine.dispose()


def retry_with_backoff(task_instance, exc: Exception, max_retries: int = 3):
    """Handle retry logic with exponential backoff."""
    if task_instance and task_instance.request.retries < max_retries:
        retry_countdown = 2 ** task_instance.request.retries * 60
        raise task_instance.retry(countdown=retry_countdown, exc=exc)
    return {"status": "error", "reason": str(exc)}
