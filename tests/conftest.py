"""
Shared pytest fixtures for InstaChatico tests.

This module provides reusable fixtures for testing the application,
including database setup, API clients, mock data, and test utilities.
"""

import pytest
import asyncio
from datetime import datetime
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

# Import app and models
from core.models.base import Base
from core.models.instagram_comment import InstagramComment
from core.models.comment_classification import CommentClassification, ProcessingStatus
from core.models.question_answer import QuestionAnswer, AnswerStatus
from core.models.media import Media
from core.config import settings


# ============================================================================
# DATABASE FIXTURES
# ============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def test_db_engine():
    """
    Create test database engine with SQLite.

    Automatically converts JSONB (PostgreSQL) to JSON (SQLite-compatible).
    """
    from sqlalchemy import JSON
    from sqlalchemy.dialects.postgresql import JSONB

    # Import all models to ensure they're loaded
    from core.models import media, instagram_comment

    # Store original types for restoration
    original_types = {}

    # Replace JSONB columns with JSON for SQLite compatibility
    # This needs to be done before metadata.create_all()
    for table_name, table in Base.metadata.tables.items():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                # Store original type
                original_types[(table_name, column.name)] = column.type
                # Replace JSONB with JSON
                column.type = JSON()

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=NullPool,
        echo=False
    )

    try:
        # Create all tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        yield engine

    finally:
        # Cleanup
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

        # Restore original JSONB types
        for (table_name, column_name), original_type in original_types.items():
            if table_name in Base.metadata.tables:
                table = Base.metadata.tables[table_name]
                for column in table.columns:
                    if column.name == column_name:
                        column.type = original_type


@pytest.fixture(scope="function")
async def test_db_session(test_db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create test database session."""
    session_factory = async_sessionmaker(
        bind=test_db_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False
    )

    async with session_factory() as session:
        yield session
        await session.rollback()


# ============================================================================
# API CLIENT FIXTURES
# ============================================================================

@pytest.fixture(scope="function")
def api_client() -> Generator[TestClient, None, None]:
    """
    FastAPI test client using TestClient.

    Automatically handles app lifespan events and provides
    synchronous interface for testing async endpoints.
    """
    import sys
    import os
    # Add src directory to path for imports
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../src'))

    # Reload settings to pick up environment changes
    import importlib
    from core import config
    importlib.reload(config)

    from main import app

    # TestClient handles lifespan automatically
    with TestClient(app, base_url="http://testserver") as client:
        yield client


# ============================================================================
# MOCK DATA FIXTURES
# ============================================================================

@pytest.fixture
def sample_media_data() -> dict:
    """Sample media data from Instagram API."""
    return {
        "id": "test_media_123",
        "permalink": "https://www.instagram.com/p/test123/",
        "caption": "Продажа квартиры в центре города",
        "media_url": "https://example.com/image.jpg",
        "media_type": "IMAGE",
        "comments_count": 5,
        "like_count": 100,
        "shortcode": "test123",
        "timestamp": "2025-10-03T10:00:00Z",
        "is_comment_enabled": True,
        "username": "test_business",
        "owner": {"id": "owner_123"}
    }


@pytest.fixture
def sample_comment_data() -> dict:
    """Sample Instagram comment data."""
    return {
        "id": "comment_123",
        "text": "Какая цена на квартиру?",
        "username": "test_user",
        "timestamp": "2025-10-03T12:00:00Z"
    }


@pytest.fixture
def sample_webhook_payload() -> dict:
    """Sample Instagram webhook payload."""
    return {
        "object": "instagram",
        "entry": [
            {
                "id": "business_account_id",
                "time": 1728000000,
                "changes": [
                    {
                        "value": {
                            "from": {
                                "id": "user_123",
                                "username": "test_user"
                            },
                            "media": {
                                "id": "media_123",
                                "media_product_type": "FEED"
                            },
                            "id": "comment_123",
                            "text": "Какая цена?"
                        },
                        "field": "comments"
                    }
                ]
            }
        ]
    }


@pytest.fixture
async def sample_media(test_db_session: AsyncSession, sample_media_data: dict) -> Media:
    """Create sample media in database."""
    media = Media(
        id=sample_media_data["id"],
        permalink=sample_media_data["permalink"],
        caption=sample_media_data["caption"],
        media_url=sample_media_data["media_url"],
        media_type=sample_media_data["media_type"],
        comments_count=sample_media_data["comments_count"],
        like_count=sample_media_data["like_count"],
        username=sample_media_data["username"],
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    test_db_session.add(media)
    await test_db_session.commit()
    await test_db_session.refresh(media)
    return media


@pytest.fixture
async def sample_comment(
    test_db_session: AsyncSession,
    sample_media: Media,
    sample_comment_data: dict
) -> InstagramComment:
    """Create sample Instagram comment in database."""
    comment = InstagramComment(
        id=sample_comment_data["id"],
        media_id=sample_media.id,
        user_id="user_123",
        username=sample_comment_data["username"],
        text=sample_comment_data["text"],
        created_at=datetime.utcnow(),
        raw_data=sample_comment_data
    )
    test_db_session.add(comment)
    await test_db_session.commit()
    await test_db_session.refresh(comment)
    return comment


# ============================================================================
# MOCK SERVICE FIXTURES
# ============================================================================

@pytest.fixture
def mock_openai_response():
    """Mock OpenAI API response."""
    mock_response = Mock()
    mock_response.choices = [Mock(message=Mock(content="Mock AI response"))]
    mock_response.usage = Mock(prompt_tokens=10, completion_tokens=20)
    return mock_response


@pytest.fixture
def mock_instagram_api():
    """Mock Instagram Graph API client."""
    with patch('core.services.instagram_service.InstagramGraphAPIService') as mock:
        instance = mock.return_value
        instance.get_media_info = AsyncMock(return_value={
            "success": True,
            "media_info": {
                "id": "media_123",
                "permalink": "https://instagram.com/p/test/",
                "caption": "Test post",
                "media_type": "IMAGE",
                "media_url": "https://example.com/image.jpg"
            }
        })
        instance.send_reply_to_comment = AsyncMock(return_value={
            "success": True,
            "reply_id": "reply_123"
        })
        yield instance


@pytest.fixture
def mock_celery_task():
    """Mock Celery task."""
    with patch('celery.app.task.Task.delay') as mock:
        mock.return_value = Mock(id="task_123")
        yield mock


# ============================================================================
# TEST UTILITIES
# ============================================================================

@pytest.fixture
def assert_validation_error():
    """Helper to assert Pydantic validation errors."""
    def _assert(func, expected_field: str):
        from pydantic import ValidationError
        with pytest.raises(ValidationError) as exc_info:
            func()
        errors = exc_info.value.errors()
        assert any(err['loc'][0] == expected_field for err in errors)
    return _assert
