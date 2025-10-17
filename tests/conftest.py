"""
Pytest configuration and shared fixtures for all tests.

This file provides:
- Database fixtures (in-memory SQLite for fast tests)
- Mock services and external APIs
- Test data factories
- FastAPI test client
- Celery test setup
"""

import asyncio
import os
import pytest
import sys
from datetime import datetime
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from faker import Faker

# Import your app modules
from core.models.base import Base
from core.models import (
    InstagramComment,
    CommentClassification,
    QuestionAnswer,
    Media,
    Document,
    ProductEmbedding,
)
from core.config import settings
from core.container import Container, get_container, reset_container
from main import app

fake = Faker()


# ============================================================================
# DATABASE FIXTURES
# ============================================================================


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def test_engine():
    """Create an in-memory SQLite database engine for testing."""
    # Use in-memory SQLite with asyncio support
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a database session for testing."""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session
        await session.rollback()


# ============================================================================
# TEST DATA FACTORIES
# ============================================================================


@pytest.fixture
def instagram_comment_factory(db_session):
    """Factory for creating test Instagram comments."""
    async def _create_comment(
        comment_id: str = None,
        media_id: str = None,
        user_id: str = None,
        username: str = None,
        text: str = None,
        parent_id: str = None,
        conversation_id: str = None,
        **kwargs
    ) -> InstagramComment:
        comment = InstagramComment(
            id=comment_id or fake.uuid4(),
            media_id=media_id or fake.uuid4(),
            user_id=user_id or fake.uuid4(),
            username=username or fake.user_name(),
            text=text or fake.sentence(),
            created_at=kwargs.get("created_at", datetime.utcnow()),
            raw_data=kwargs.get("raw_data", {}),
            parent_id=parent_id,
            conversation_id=conversation_id,
            is_hidden=kwargs.get("is_hidden", False),
        )
        db_session.add(comment)
        await db_session.commit()
        await db_session.refresh(comment)
        return comment

    return _create_comment


@pytest.fixture
def media_factory(db_session):
    """Factory for creating test Media objects."""
    async def _create_media(
        media_id: str = None,
        media_type: str = "IMAGE",
        url: str = None,
        caption: str = None,
        **kwargs
    ) -> Media:
        media = Media(
            id=media_id or fake.uuid4(),
            media_type=media_type,
            url=url or fake.image_url(),
            caption=caption or fake.text(),
            permalink=kwargs.get("permalink", fake.url()),
            media_context=kwargs.get("media_context"),
            children_media_urls=kwargs.get("children_media_urls"),
            created_at=kwargs.get("created_at", datetime.utcnow()),
        )
        db_session.add(media)
        await db_session.commit()
        await db_session.refresh(media)
        return media

    return _create_media


@pytest.fixture
def classification_factory(db_session):
    """Factory for creating test comment classifications."""
    async def _create_classification(
        comment_id: str,
        classification: str = "question / inquiry",
        confidence: float = 0.95,
        **kwargs
    ) -> CommentClassification:
        clf = CommentClassification(
            comment_id=comment_id,
            classification=classification,
            confidence=confidence,
            reasoning=kwargs.get("reasoning", "Test reasoning"),
            retry_count=kwargs.get("retry_count", 0),
            input_tokens=kwargs.get("input_tokens", 100),
            output_tokens=kwargs.get("output_tokens", 50),
            created_at=kwargs.get("created_at", datetime.utcnow()),
        )
        db_session.add(clf)
        await db_session.commit()
        await db_session.refresh(clf)
        return clf

    return _create_classification


@pytest.fixture
def answer_factory(db_session):
    """Factory for creating test answers."""
    async def _create_answer(
        comment_id: str,
        question_text: str = None,
        answer_text: str = None,
        **kwargs
    ) -> QuestionAnswer:
        answer = QuestionAnswer(
            comment_id=comment_id,
            question_text=question_text or fake.sentence(nb_words=10),
            answer_text=answer_text or fake.text(),
            confidence=kwargs.get("confidence", 0.9),
            quality_score=kwargs.get("quality_score", 0.85),
            processing_time_ms=kwargs.get("processing_time_ms", 1500),
            input_tokens=kwargs.get("input_tokens", 200),
            output_tokens=kwargs.get("output_tokens", 150),
            created_at=kwargs.get("created_at", datetime.utcnow()),
        )
        db_session.add(answer)
        await db_session.commit()
        await db_session.refresh(answer)
        return answer

    return _create_answer


# ============================================================================
# API CLIENT FIXTURES
# ============================================================================


@pytest.fixture
def test_client() -> TestClient:
    """Sync FastAPI test client for testing endpoints."""
    return TestClient(app)


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Async FastAPI test client for testing async endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ============================================================================
# DEPENDENCY INJECTION FIXTURES
# ============================================================================


@pytest.fixture
def test_container():
    """Create a test DI container with mocked dependencies."""
    reset_container()
    container = Container()

    # Override with test configuration if needed
    # container.config.from_dict({"test_mode": True})

    yield container

    reset_container()


@pytest.fixture
def override_get_container(test_container):
    """Override the get_container dependency."""
    def _get_test_container():
        return test_container

    app.dependency_overrides[get_container] = _get_test_container
    yield
    app.dependency_overrides.clear()


# ============================================================================
# MOCK SERVICE FIXTURES
# ============================================================================


@pytest.fixture
def mock_openai_response():
    """Mock OpenAI API response."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Test AI response"
    mock_response.usage.prompt_tokens = 100
    mock_response.usage.completion_tokens = 50
    mock_response.usage.total_tokens = 150
    return mock_response


@pytest.fixture
def mock_instagram_api():
    """Mock Instagram Graph API responses."""
    with patch("core.services.instagram_service.InstagramGraphAPIService") as mock:
        instance = mock.return_value
        instance.post_reply = AsyncMock(return_value={"id": "reply_123"})
        instance.hide_comment = AsyncMock(return_value={"success": True})
        instance.get_media = AsyncMock(return_value={
            "id": "media_123",
            "media_type": "IMAGE",
            "media_url": "https://example.com/image.jpg",
            "caption": "Test caption"
        })
        yield instance


@pytest.fixture
def mock_telegram_api():
    """Mock Telegram API responses."""
    with patch("core.services.telegram_alert_service.TelegramAlertService") as mock:
        instance = mock.return_value
        instance.send_alert = AsyncMock(return_value={"ok": True, "result": {"message_id": 123}})
        yield instance


@pytest.fixture
def mock_embedding_service():
    """Mock embedding service for vector search."""
    with patch("core.services.embedding_service.EmbeddingService") as mock:
        instance = mock.return_value
        instance.search_similar_products = AsyncMock(return_value=[
            {
                "title": "Test Product",
                "description": "Test description",
                "similarity": 0.95,
                "price": "100 @C1",
                "is_ood": False,
            }
        ])
        instance.create_embedding = AsyncMock(return_value=[0.1] * 1536)
        yield instance


@pytest.fixture
def mock_s3_service():
    """Mock S3 service for file storage."""
    with patch("core.services.s3_service.S3Service") as mock:
        instance = mock.return_value
        instance.upload_file = AsyncMock(return_value="s3://bucket/file.pdf")
        instance.download_file = AsyncMock(return_value=b"file content")
        instance.delete_file = AsyncMock(return_value=True)
        yield instance


@pytest.fixture
def mock_celery_task_queue():
    """Mock Celery task queue."""
    with patch("core.infrastructure.task_queue.CeleryTaskQueue") as mock:
        instance = mock.return_value
        instance.enqueue = MagicMock(return_value="task_123")
        yield instance


# ============================================================================
# AGENT TOOL FIXTURES
# ============================================================================


@pytest.fixture
def mock_agent_runner():
    """Mock OpenAI Agents SDK Runner."""
    with patch("agents.Runner") as mock:
        mock_result = MagicMock()
        mock_result.final_output = "Test agent response"
        mock_result.raw_responses = [MagicMock()]
        mock_result.raw_responses[0].usage.input_tokens = 100
        mock_result.raw_responses[0].usage.output_tokens = 50

        mock.run = AsyncMock(return_value=mock_result)
        yield mock


# ============================================================================
# ENVIRONMENT FIXTURES
# ============================================================================


@pytest.fixture
def test_env_vars():
    """Set test environment variables."""
    original_env = os.environ.copy()

    test_vars = {
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "CELERY_BROKER_URL": "redis://localhost:6379/0",
        "OPENAI_API_KEY": "test_key",
        "INSTA_TOKEN": "test_token",
        "APP_SECRET": "test_secret",
        "DEVELOPMENT_MODE": "true",
    }

    os.environ.update(test_vars)
    yield test_vars

    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


# ============================================================================
# UTILITY FIXTURES
# ============================================================================


@pytest.fixture
def sample_webhook_payload():
    """Sample Instagram webhook payload."""
    return {
        "object": "instagram",
        "entry": [
            {
                "id": "instagram_business_account_id",
                "time": 1234567890,
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "id": "comment_123",
                            "media": {
                                "id": "media_123",
                                "media_product_type": "FEED"
                            },
                            "text": "!:>;L:> AB>8B 4>AB02:0?",
                            "from": {
                                "id": "user_123",
                                "username": "test_user"
                            }
                        }
                    }
                ]
            }
        ]
    }
