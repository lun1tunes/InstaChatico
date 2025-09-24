"""
Base classes and utilities for Celery tasks.
Provides common functionality for all task types.
"""

import asyncio
import time
from datetime import datetime
from typing import Dict, Any, Optional, Callable
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from ..config import settings
from ..logging_config import get_logger
from ..exceptions import TaskError, DatabaseError


class TaskResult:
    """Standardized task result format"""
    
    def __init__(
        self,
        success: bool,
        data: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        processing_time_ms: Optional[int] = None
    ):
        self.success = success
        self.data = data or {}
        self.error = error
        self.processing_time_ms = processing_time_ms
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Celery return value"""
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "processing_time_ms": self.processing_time_ms,
            "timestamp": datetime.utcnow().isoformat()
        }


class BaseTaskExecutor:
    """Base class for executing async tasks in Celery"""
    
    def __init__(self, task_name: str):
        self.task_name = task_name
        self.logger = get_logger(f"task.{task_name}", task_name)
    
    async def create_db_session(self) -> AsyncSession:
        """Create a fresh database session for the task"""
        try:
            engine = create_async_engine(
                settings.db.url,
                echo=settings.db.echo,
                pool_pre_ping=True
            )
            session_factory = async_sessionmaker(
                bind=engine,
                autoflush=False,
                autocommit=False,
                expire_on_commit=False
            )
            
            session = session_factory()
            return session, engine
            
        except Exception as e:
            self.logger.error(
                "Failed to create database session",
                extra_fields={"error": str(e)},
                operation="create_db_session"
            )
            raise DatabaseError(f"Database connection failed: {str(e)}")
    
    async def execute_with_session(
        self,
        operation: Callable,
        *args,
        **kwargs
    ) -> TaskResult:
        """
        Execute an async operation with proper database session management.
        
        Args:
            operation: Async function to execute
            *args: Arguments for the operation
            **kwargs: Keyword arguments for the operation
            
        Returns:
            TaskResult with operation outcome
        """
        start_time = time.time()
        session = None
        engine = None
        
        try:
            # Create database session
            session, engine = await self.create_db_session()
            
            self.logger.info(
                f"Starting task {self.task_name}",
                operation=self.task_name
            )
            
            # Execute the operation
            result = await operation(session, *args, **kwargs)
            
            processing_time_ms = int((time.time() - start_time) * 1000)
            
            self.logger.info(
                f"Task {self.task_name} completed successfully",
                extra_fields={"processing_time_ms": processing_time_ms},
                operation=self.task_name
            )
            
            return TaskResult(
                success=True,
                data=result if isinstance(result, dict) else {"result": result},
                processing_time_ms=processing_time_ms
            )
            
        except Exception as e:
            processing_time_ms = int((time.time() - start_time) * 1000)
            
            if session:
                await session.rollback()
            
            self.logger.error(
                f"Task {self.task_name} failed",
                extra_fields={
                    "error": str(e),
                    "processing_time_ms": processing_time_ms
                },
                operation=self.task_name
            )
            
            return TaskResult(
                success=False,
                error=str(e),
                processing_time_ms=processing_time_ms
            )
            
        finally:
            # Cleanup resources
            if session:
                await session.close()
            if engine:
                await engine.dispose()
    
    def run_async_task(
        self,
        operation: Callable,
        *args,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Run an async operation in a new event loop (for Celery sync tasks).
        
        Args:
            operation: Async function to execute
            *args: Arguments for the operation  
            **kwargs: Keyword arguments for the operation
            
        Returns:
            Task result dictionary
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                self.execute_with_session(operation, *args, **kwargs)
            )
            return result.to_dict()
        finally:
            loop.close()


class RetryableTask:
    """Mixin for tasks that support retry logic"""
    
    def __init__(self, max_retries: int = 3, retry_delay: int = 60):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
    
    def should_retry(self, retry_count: int, error: Exception) -> bool:
        """
        Determine if task should be retried based on error type and retry count.
        
        Args:
            retry_count: Current retry attempt
            error: Exception that caused the failure
            
        Returns:
            True if task should be retried
        """
        if retry_count >= self.max_retries:
            return False
        
        # Don't retry certain types of errors
        non_retryable_errors = [
            "ValidationError",
            "AuthenticationError", 
            "NotFoundError"
        ]
        
        error_type = type(error).__name__
        if any(err in error_type for err in non_retryable_errors):
            return False
        
        return True
    
    def get_retry_delay(self, retry_count: int) -> int:
        """
        Calculate retry delay with exponential backoff.
        
        Args:
            retry_count: Current retry attempt
            
        Returns:
            Delay in seconds before next retry
        """
        return self.retry_delay * (2 ** retry_count)


def create_task_logger(task_name: str):
    """Create a standardized logger for tasks"""
    return get_logger(f"task.{task_name}", task_name)


def log_task_start(logger, task_name: str, **context):
    """Standardized task start logging"""
    logger.info(
        f"Task {task_name} started",
        extra_fields=context,
        operation=task_name
    )


def log_task_success(logger, task_name: str, processing_time_ms: int, **context):
    """Standardized task success logging"""
    logger.info(
        f"Task {task_name} completed successfully",
        extra_fields={
            "processing_time_ms": processing_time_ms,
            **context
        },
        operation=task_name
    )


def log_task_error(logger, task_name: str, error: str, retry_count: int = 0, **context):
    """Standardized task error logging"""
    logger.error(
        f"Task {task_name} failed",
        extra_fields={
            "error": error,
            "retry_count": retry_count,
            **context
        },
        operation=task_name
    )


def log_task_retry(logger, task_name: str, retry_count: int, delay: int, **context):
    """Standardized task retry logging"""
    logger.warning(
        f"Task {task_name} will retry in {delay} seconds",
        extra_fields={
            "retry_count": retry_count,
            "retry_delay": delay,
            **context
        },
        operation=task_name
    )
