"""Unit tests for task helper utilities."""

import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock, Mock
from functools import wraps

from core.utils.task_helpers import (
    _get_worker_event_loop,
    async_task,
    get_db_session,
    retry_with_backoff
)


@pytest.mark.unit
class TestGetWorkerEventLoop:
    """Test _get_worker_event_loop function."""

    def test_get_worker_event_loop_creates_new_loop(self):
        """Test that _get_worker_event_loop creates a new event loop on first call."""
        # Arrange - Clear any cached loop
        if hasattr(_get_worker_event_loop, '_loop'):
            delattr(_get_worker_event_loop, '_loop')

        # Act
        loop = _get_worker_event_loop()

        # Assert
        assert isinstance(loop, asyncio.AbstractEventLoop)

    def test_get_worker_event_loop_returns_same_loop(self):
        """Test that _get_worker_event_loop returns the same loop on subsequent calls."""
        # Arrange - Clear any cached loop
        if hasattr(_get_worker_event_loop, '_loop'):
            delattr(_get_worker_event_loop, '_loop')

        # Act
        loop1 = _get_worker_event_loop()
        loop2 = _get_worker_event_loop()

        # Assert
        assert loop1 is loop2

    def test_get_worker_event_loop_caches_loop(self):
        """Test that the loop is cached on the function object."""
        # Arrange - Clear any cached loop
        if hasattr(_get_worker_event_loop, '_loop'):
            delattr(_get_worker_event_loop, '_loop')

        # Act
        loop = _get_worker_event_loop()

        # Assert
        assert hasattr(_get_worker_event_loop, '_loop')
        assert _get_worker_event_loop._loop is loop


@pytest.mark.unit
class TestAsyncTask:
    """Test async_task decorator."""

    def test_async_task_decorator_runs_async_function(self):
        """Test that async_task decorator runs an async function."""
        # Arrange
        async def my_async_function(x, y):
            await asyncio.sleep(0.001)
            return x + y

        # Decorate the function
        decorated = async_task(my_async_function)

        # Act
        result = decorated(5, 3)

        # Assert
        assert result == 8

    def test_async_task_sets_event_loop(self):
        """Test that async_task sets the event loop."""
        # Arrange
        async def my_task():
            return "done"

        decorated = async_task(my_task)

        worker_loop = asyncio.new_event_loop()
        current_loop = asyncio.new_event_loop()

        class DummyPolicy:
            def get_event_loop(self_inner):
                return current_loop

        try:
            with patch.object(_get_worker_event_loop, '_loop', new=worker_loop, create=True):
                with patch('asyncio.set_event_loop') as mock_set_loop, \
                     patch('asyncio.get_event_loop_policy', return_value=DummyPolicy()):
                    result = decorated()

            assert result == "done"
            mock_set_loop.assert_called_once_with(worker_loop)
        finally:
            worker_loop.close()
            current_loop.close()
            if hasattr(_get_worker_event_loop, "_loop"):
                delattr(_get_worker_event_loop, "_loop")

    def test_async_task_skips_setting_loop_when_already_current(self):
        """async_task should not reset the loop if it is already current."""
        async def my_task():
            return "done"

        decorated = async_task(my_task)

        loop = asyncio.new_event_loop()
        original_loop = getattr(_get_worker_event_loop, "_loop", None)

        class DummyPolicy:
            def get_event_loop(self_inner):
                return loop

        try:
            _get_worker_event_loop._loop = loop
            with patch('asyncio.get_event_loop_policy', return_value=DummyPolicy()) as mock_policy, \
                 patch('asyncio.set_event_loop') as mock_set_loop:
                result = decorated()

            assert result == "done"
            mock_set_loop.assert_not_called()
            # Ensure helper asked policy for current loop
            assert mock_policy.called
        finally:
            loop.close()
            if original_loop is not None:
                _get_worker_event_loop._loop = original_loop
            elif hasattr(_get_worker_event_loop, "_loop"):
                delattr(_get_worker_event_loop, "_loop")

    def test_async_task_preserves_function_metadata(self):
        """Test that async_task preserves the original function's metadata."""
        # Arrange
        async def my_documented_task():
            """This is my task documentation."""
            return "result"

        # Act
        decorated = async_task(my_documented_task)

        # Assert
        assert decorated.__name__ == "my_documented_task"
        assert "my task documentation" in decorated.__doc__.lower()

    def test_async_task_with_args_and_kwargs(self):
        """Test async_task with positional and keyword arguments."""
        # Arrange
        async def my_task(pos1, pos2, kwarg1=None, kwarg2="default"):
            return f"{pos1}-{pos2}-{kwarg1}-{kwarg2}"

        decorated = async_task(my_task)

        # Act
        result = decorated("a", "b", kwarg1="c", kwarg2="d")

        # Assert
        assert result == "a-b-c-d"

    def test_async_task_handles_exceptions(self):
        """Test that async_task propagates exceptions from async function."""
        # Arrange
        async def failing_task():
            raise ValueError("Task failed")

        decorated = async_task(failing_task)

        # Act & Assert
        with pytest.raises(ValueError, match="Task failed"):
            decorated()


@pytest.mark.unit
class TestGetDbSession:
    """Test get_db_session context manager."""

    @pytest.mark.asyncio
    async def test_get_db_session_yields_session(self):
        """Test that get_db_session yields a database session."""
        # Arrange
        mock_session = AsyncMock()
        mock_session_factory = MagicMock()

        # Create async context manager mock
        async def async_context():
            yield mock_session

        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_container = MagicMock()
        mock_container.db_session_factory.return_value = mock_session_factory

        # Act
        with patch('core.utils.task_helpers.get_container', return_value=mock_container):
            async with get_db_session() as session:
                result_session = session

        # Assert
        assert result_session == mock_session

    @pytest.mark.asyncio
    async def test_get_db_session_uses_container(self):
        """Test that get_db_session uses the container to get session factory."""
        # Arrange
        mock_session = AsyncMock()
        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_container = MagicMock()
        mock_container.db_session_factory.return_value = mock_session_factory

        # Act
        with patch('core.utils.task_helpers.get_container') as mock_get_container:
            mock_get_container.return_value = mock_container

            async with get_db_session() as session:
                pass

        # Assert
        mock_get_container.assert_called_once()
        mock_container.db_session_factory.assert_called_once()


@pytest.mark.unit
class TestRetryWithBackoff:
    """Test retry_with_backoff function."""

    def test_retry_with_backoff_first_attempt(self):
        """Test retry with backoff on first attempt (retry count 0)."""
        # Arrange
        mock_task = MagicMock()
        mock_task.request.retries = 0
        mock_task.retry = MagicMock(side_effect=Exception("Retry scheduled"))
        exc = ValueError("Test error")

        # Act & Assert
        with pytest.raises(Exception, match="Retry scheduled"):
            retry_with_backoff(mock_task, exc, max_retries=3)

        # Assert - countdown should be 2^0 * 60 = 60 seconds
        mock_task.retry.assert_called_once_with(countdown=60, exc=exc)

    def test_retry_with_backoff_second_attempt(self):
        """Test retry with backoff on second attempt (retry count 1)."""
        # Arrange
        mock_task = MagicMock()
        mock_task.request.retries = 1
        mock_task.retry = MagicMock(side_effect=Exception("Retry scheduled"))
        exc = RuntimeError("Test error")

        # Act & Assert
        with pytest.raises(Exception, match="Retry scheduled"):
            retry_with_backoff(mock_task, exc, max_retries=3)

        # Assert - countdown should be 2^1 * 60 = 120 seconds
        mock_task.retry.assert_called_once_with(countdown=120, exc=exc)

    def test_retry_with_backoff_max_retries_reached(self):
        """Test retry with backoff when max retries is reached."""
        # Arrange
        mock_task = MagicMock()
        mock_task.request.retries = 3
        exc = ValueError("Final error")

        # Act
        result = retry_with_backoff(mock_task, exc, max_retries=3)

        # Assert
        assert result["status"] == "error"
        assert "Final error" in result["reason"]
        mock_task.retry.assert_not_called()

    def test_retry_with_backoff_none_task_instance(self):
        """Test retry with backoff when task_instance is None."""
        # Arrange
        exc = ValueError("Error with no task")

        # Act
        result = retry_with_backoff(None, exc, max_retries=3)

        # Assert
        assert result["status"] == "error"
        assert "Error with no task" in result["reason"]

    def test_retry_with_backoff_exponential_backoff(self):
        """Test that retry countdown follows exponential backoff pattern."""
        # Arrange
        exc = Exception("Test")

        # Test different retry counts
        for retry_count in range(5):
            mock_task = MagicMock()
            mock_task.request.retries = retry_count
            mock_task.retry = MagicMock(side_effect=Exception("Retry"))

            expected_countdown = (2 ** retry_count) * 60

            # Act & Assert
            try:
                retry_with_backoff(mock_task, exc, max_retries=10)
            except Exception:
                pass

            # Assert
            if retry_count < 10:
                mock_task.retry.assert_called_once_with(countdown=expected_countdown, exc=exc)

    def test_retry_with_backoff_custom_max_retries(self):
        """Test retry with custom max_retries value."""
        # Arrange
        mock_task = MagicMock()
        mock_task.request.retries = 4
        mock_task.retry = MagicMock(side_effect=Exception("Retry scheduled"))
        exc = ValueError("Test error")

        # Act & Assert - Should retry since 4 < 5
        with pytest.raises(Exception, match="Retry scheduled"):
            retry_with_backoff(mock_task, exc, max_retries=5)

        mock_task.retry.assert_called_once()

        # Test when max is reached
        mock_task2 = MagicMock()
        mock_task2.request.retries = 5
        result2 = retry_with_backoff(mock_task2, exc, max_retries=5)

        # Assert - Should not retry
        assert result2["status"] == "error"
