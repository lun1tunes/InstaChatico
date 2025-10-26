"""Pagination and filtering tests for JSON API endpoints."""

import pytest
from httpx import AsyncClient

from core.models import CommentClassification, InstagramComment, Media
from core.models.comment_classification import ProcessingStatus
from core.utils.time import now_db_utc
from tests.integration.json_api_helpers import auth_headers


# ===== Media Endpoints Tests =====


@pytest.mark.asyncio
async def test_get_media_by_id(integration_environment):
    """Test getting a single media by ID."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_detail_test",
            permalink="https://instagram.com/p/media_detail_test",
            media_type="VIDEO",
            media_url="https://cdn.test/video.mp4",
            caption="Test video caption",
            is_processing_enabled=True,
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        await session.commit()

    response = await client.get("/api/v1/media/media_detail_test", headers=auth_headers(integration_environment))
    assert response.status_code == 200
    data = response.json()
    assert data["payload"]["id"] == "media_detail_test"
    assert data["payload"]["type"] == 2  # VIDEO = 2
    assert data["payload"]["caption"] == "Test video caption"
    assert data["payload"]["is_processing_enabled"] is True


@pytest.mark.asyncio
async def test_get_media_not_found(integration_environment):
    """Test getting non-existent media returns 404."""
    client: AsyncClient = integration_environment["client"]
    response = await client.get("/api/v1/media/nonexistent_media", headers=auth_headers(integration_environment))
    assert response.status_code == 404
    data = response.json()
    assert data["meta"]["error"]["code"] == 4040
    assert "Media not found" in data["meta"]["error"]["message"]


@pytest.mark.asyncio
async def test_patch_media_processing_enabled(integration_environment):
    """Test toggling media is_processing_enabled field."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_toggle_processing",
            permalink="https://instagram.com/p/media_toggle_processing",
            media_type="IMAGE",
            media_url="https://cdn.test/toggle.jpg",
            is_processing_enabled=True,
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        await session.commit()

    # Disable processing
    response = await client.patch(
        "/api/v1/media/media_toggle_processing",
        headers=auth_headers(integration_environment),
        json={"is_processing_enabled": False},
    )
    assert response.status_code == 200
    payload = response.json()["payload"]
    assert payload["is_processing_enabled"] is False

    # Verify in database
    async with session_factory() as session:
        media = await session.get(Media, "media_toggle_processing")
        assert media.is_processing_enabled is False


@pytest.mark.asyncio
async def test_patch_media_context(integration_environment):
    """Test updating media context field."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_context_test",
            permalink="https://instagram.com/p/media_context_test",
            media_type="IMAGE",
            media_url="https://cdn.test/context.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        await session.commit()

    response = await client.patch(
        "/api/v1/media/media_context_test",
        headers=auth_headers(integration_environment),
        json={"context": "This is a promotional post for our new product"},
    )
    assert response.status_code == 200
    payload = response.json()["payload"]
    assert payload["context"] == "This is a promotional post for our new product"


@pytest.mark.asyncio
async def test_patch_media_comment_status(integration_environment):
    """Test toggling media comment enabled status via Instagram API."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    instagram_service = integration_environment["instagram_service"]

    async with session_factory() as session:
        media = Media(
            id="media_comment_toggle",
            permalink="https://instagram.com/p/media_comment_toggle",
            media_type="IMAGE",
            media_url="https://cdn.test/comment_toggle.jpg",
            is_comment_enabled=True,
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        await session.commit()

    response = await client.patch(
        "/api/v1/media/media_comment_toggle",
        headers=auth_headers(integration_environment),
        json={"is_comment_enabled": False},
    )
    assert response.status_code == 200
    payload = response.json()["payload"]
    assert payload["is_comment_enabled"] is False


# ===== Pagination Tests =====


@pytest.mark.asyncio
async def test_media_list_pagination_default(integration_environment):
    """Test media listing with default pagination."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    # Create 15 media items
    async with session_factory() as session:
        for i in range(15):
            media = Media(
                id=f"pagination_media_{i}",
                permalink=f"https://instagram.com/p/pagination_media_{i}",
                media_type="IMAGE",
                media_url=f"https://cdn.test/page{i}.jpg",
                created_at=now_db_utc(),
                updated_at=now_db_utc(),
            )
            session.add(media)
        await session.commit()

    response = await client.get("/api/v1/media", headers=auth_headers(integration_environment))
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["page"] == 1
    assert data["meta"]["per_page"] == 10  # Default
    assert data["meta"]["total"] >= 15
    assert len(data["payload"]) == 10


@pytest.mark.asyncio
async def test_media_list_pagination_custom_per_page(integration_environment):
    """Test media listing with custom per_page parameter."""
    client: AsyncClient = integration_environment["client"]
    response = await client.get("/api/v1/media?per_page=5", headers=auth_headers(integration_environment))
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["per_page"] == 5
    assert len(data["payload"]) <= 5


@pytest.mark.asyncio
async def test_media_list_pagination_max_clamped(integration_environment):
    """Test media listing clamps per_page to maximum."""
    client: AsyncClient = integration_environment["client"]
    response = await client.get("/api/v1/media?per_page=1000", headers=auth_headers(integration_environment))
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["per_page"] == 30  # Max for media


@pytest.mark.asyncio
async def test_media_list_page_2(integration_environment):
    """Test media listing on page 2."""
    client: AsyncClient = integration_environment["client"]
    response = await client.get("/api/v1/media?page=2&per_page=5", headers=auth_headers(integration_environment))
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["page"] == 2


@pytest.mark.asyncio
async def test_media_list_invalid_page_returns_422(integration_environment):
    """Requesting page=0 should trigger validation error wrapped in JSON API envelope."""
    client: AsyncClient = integration_environment["client"]
    response = await client.get("/api/v1/media?page=0", headers=auth_headers(integration_environment))
    assert response.status_code == 422
    body = response.json()
    assert body["meta"]["error"]["code"] == 4000
    assert body["payload"] is None


@pytest.mark.asyncio
async def test_comment_list_per_page_clamped(integration_environment):
    """Comments listing should enforce MAX_PER_PAGE of 100."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    media_id = "media_comments_pagination"
    async with session_factory() as session:
        media = Media(
            id=media_id,
            permalink="https://instagram.com/p/media_comments_pagination",
            media_type="IMAGE",
            media_url="https://cdn.test/comments_pag.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        # Add a handful of comments to ensure payload is non-empty
        for idx in range(5):
            comment = InstagramComment(
                id=f"comment_pag_{idx}",
                media_id=media_id,
                user_id=f"user_{idx}",
                username=f"user_{idx}",
                text=f"Comment {idx}",
                created_at=now_db_utc(),
                raw_data={},
            )
            session.add(comment)
            session.add(
                CommentClassification(
                    comment_id=comment.id,
                    processing_status=ProcessingStatus.COMPLETED,
                )
            )
        await session.commit()

    response = await client.get(
        f"/api/v1/media/{media_id}/comments?per_page=500",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["per_page"] == 100  # MAX_PER_PAGE for comments
    assert len(payload["payload"]) <= 100

