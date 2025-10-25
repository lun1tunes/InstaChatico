import pytest
from httpx import AsyncClient

from core.models import CommentClassification, InstagramComment, Media, QuestionAnswer
from core.utils.time import now_db_utc


def auth_headers(env):
    return {"Authorization": f"Bearer {env['json_api_token']}"}


@pytest.mark.asyncio
async def test_media_listing(integration_environment):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_list",
            permalink="https://instagram.com/p/media_list",
            media_type="IMAGE",
            media_url="https://cdn.test/list.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        await session.commit()

    response = await client.get("/api/v1/media", headers=auth_headers(integration_environment))
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["page"] == 1
    assert len(data["payload"]) >= 1
    first = data["payload"][0]
    assert "is_processing_enabled" in first


@pytest.mark.asyncio
async def test_media_comments_with_status_filter(integration_environment):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_comments",
            permalink="https://instagram.com/p/media_comments",
            media_type="IMAGE",
            media_url="https://cdn.test/comments.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)

        comment = InstagramComment(
            id="comment_status",
            media_id=media.id,
            user_id="user",
            username="tester",
            text="Needs attention",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)

        classification = CommentClassification(
            comment_id=comment.id,
            type="question / inquiry",
            processing_status="COMPLETED",
            processing_completed_at=now_db_utc(),
        )
        session.add(classification)
        await session.commit()

    response = await client.get(
        "/api/v1/media/media_comments/comments?status[]=3",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    payload = response.json()["payload"]
    assert len(payload) == 1
    assert payload[0]["classification"]["type"] == 4


@pytest.mark.asyncio
async def test_patch_comment_classification(integration_environment):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_patch_classification",
            permalink="https://instagram.com/p/media_patch_classification",
            media_type="IMAGE",
            media_url="https://cdn.test/patch.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        comment = InstagramComment(
            id="comment_patch_classification",
            media_id=media.id,
            user_id="user",
            username="tester",
            text="Original",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        classification = CommentClassification(
            comment_id=comment.id,
            type="positive feedback",
            processing_status="COMPLETED",
            confidence=85,
            reasoning="auto",
        )
        session.add(classification)
        await session.commit()

    response = await client.patch(
        "/api/v1/comments/comment_patch_classification/classification",
        headers=auth_headers(integration_environment),
        json={"type": "critical feedback", "reasoning": "manual review"},
    )
    assert response.status_code == 200
    payload = response.json()["payload"]
    assert payload["classification"]["type"] == 2
    assert payload["classification"]["confidence"] is None


@pytest.mark.asyncio
async def test_answer_management(integration_environment):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_answer",
            permalink="https://instagram.com/p/media_answer",
            media_type="IMAGE",
            media_url="https://cdn.test/answer.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        comment = InstagramComment(
            id="comment_answer",
            media_id=media.id,
            user_id="user",
            username="tester",
            text="Answer me",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        answer = QuestionAnswer(
            id=999,
            comment_id=comment.id,
            answer="Old answer",
            answer_confidence=0.5,
            answer_quality_score=70,
            reply_sent=True,
            reply_status="sent",
            reply_id="ig_reply_1",
            processing_status="COMPLETED",
        )
        session.add(answer)
        await session.commit()

    update = await client.patch(
        "/api/v1/answers/999",
        headers=auth_headers(integration_environment),
        json={"answer": "New answer", "confidence": 80},
    )
    assert update.status_code == 200
    assert update.json()["payload"]["confidence"] == 80

    delete = await client.delete(
        "/api/v1/answers/999",
        headers=auth_headers(integration_environment),
    )
    assert delete.status_code == 200
    assert delete.json()["payload"] is None


# ===== Authentication Tests =====


@pytest.mark.asyncio
async def test_media_list_missing_auth_header(integration_environment):
    """Test that media listing requires authentication."""
    client: AsyncClient = integration_environment["client"]
    response = await client.get("/api/v1/media")
    assert response.status_code == 401
    data = response.json()
    assert data["meta"]["error"]["code"] == 4001
    assert "Missing or invalid Authorization header" in data["meta"]["error"]["message"]


@pytest.mark.asyncio
async def test_media_list_invalid_auth_format(integration_environment):
    """Test that media listing rejects invalid auth format."""
    client: AsyncClient = integration_environment["client"]
    response = await client.get("/api/v1/media", headers={"Authorization": "InvalidFormat token123"})
    assert response.status_code == 401
    data = response.json()
    assert data["meta"]["error"]["code"] == 4001


@pytest.mark.asyncio
async def test_media_list_wrong_token(integration_environment):
    """Test that media listing rejects wrong token."""
    client: AsyncClient = integration_environment["client"]
    response = await client.get("/api/v1/media", headers={"Authorization": "Bearer wrong-token"})
    assert response.status_code == 401
    data = response.json()
    assert data["meta"]["error"]["code"] == 4002
    assert "Unauthorized" in data["meta"]["error"]["message"]


@pytest.mark.asyncio
async def test_comment_hide_unauthorized(integration_environment):
    """Test that comment visibility endpoint requires authentication."""
    client: AsyncClient = integration_environment["client"]
    response = await client.patch("/api/v1/comments/comment_123", json={"is_hidden": True})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_answer_patch_unauthorized(integration_environment):
    """Test that answer update requires authentication."""
    client: AsyncClient = integration_environment["client"]
    response = await client.patch("/api/v1/answers/1", json={"answer": "test"})
    assert response.status_code == 401


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


# ===== Comment Visibility Tests =====


@pytest.mark.asyncio
async def test_hide_comment(integration_environment):
    """Test hiding a comment via API."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    instagram_service = integration_environment["instagram_service"]

    async with session_factory() as session:
        media = Media(
            id="media_hide_test",
            permalink="https://instagram.com/p/media_hide_test",
            media_type="IMAGE",
            media_url="https://cdn.test/hide.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        comment = InstagramComment(
            id="comment_to_hide",
            media_id=media.id,
            user_id="user_spam",
            username="spammer",
            text="Spam comment",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        await session.commit()

    response = await client.patch(
        "/api/v1/comments/comment_to_hide",
        headers=auth_headers(integration_environment),
        json={"is_hidden": True},
    )
    assert response.status_code == 200
    assert "comment_to_hide" in instagram_service.hidden


@pytest.mark.asyncio
async def test_unhide_comment(integration_environment):
    """Test unhiding a comment via API."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    instagram_service = integration_environment["instagram_service"]

    async with session_factory() as session:
        media = Media(
            id="media_unhide_test",
            permalink="https://instagram.com/p/media_unhide_test",
            media_type="IMAGE",
            media_url="https://cdn.test/unhide.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        comment = InstagramComment(
            id="comment_to_unhide",
            media_id=media.id,
            user_id="user_ok",
            username="gooduser",
            text="Good comment",
            is_hidden=True,  # Start as hidden
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        await session.commit()

    # Pre-populate as hidden in Instagram service stub
    instagram_service.hidden.append("comment_to_unhide")

    # Then unhide via API
    response = await client.patch(
        "/api/v1/comments/comment_to_unhide",
        headers=auth_headers(integration_environment),
        json={"is_hidden": False},
    )
    assert response.status_code == 200
    assert "comment_to_unhide" not in instagram_service.hidden


@pytest.mark.asyncio
async def test_hide_comment_not_found(integration_environment):
    """Test hiding non-existent comment returns 502 (use case returns error, then 404 when fetching after)."""
    client: AsyncClient = integration_environment["client"]
    response = await client.patch(
        "/api/v1/comments/nonexistent_comment",
        headers=auth_headers(integration_environment),
        json={"is_hidden": True},
    )
    # The use case returns error status first, causing 502
    assert response.status_code == 502
    data = response.json()
    assert data["meta"]["error"]["code"] == 5003


# ===== Comment Deletion Tests =====


@pytest.mark.asyncio
async def test_delete_comment(integration_environment):
    """Test deleting a comment via API."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_delete_test",
            permalink="https://instagram.com/p/media_delete_test",
            media_type="IMAGE",
            media_url="https://cdn.test/delete.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        comment = InstagramComment(
            id="comment_to_delete",
            media_id=media.id,
            user_id="user_del",
            username="deluser",
            text="Will be deleted",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        await session.commit()

    response = await client.delete(
        "/api/v1/comments/comment_to_delete",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    assert response.json()["payload"] is None

    # Verify deleted from database
    async with session_factory() as session:
        deleted = await session.get(InstagramComment, "comment_to_delete")
        assert deleted is None


# ===== Status Filter Tests =====


@pytest.mark.asyncio
async def test_media_comments_filter_by_csv_status(integration_environment):
    """Test filtering comments by CSV status parameter."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_csv_filter",
            permalink="https://instagram.com/p/media_csv_filter",
            media_type="IMAGE",
            media_url="https://cdn.test/csv.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)

        # Add comment with PENDING status
        comment = InstagramComment(
            id="comment_csv_pending",
            media_id=media.id,
            user_id="user",
            username="tester",
            text="Pending comment",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        classification = CommentClassification(
            comment_id=comment.id,
            type="question / inquiry",
            processing_status="PENDING",
        )
        session.add(classification)
        await session.commit()

    # Use CSV format for status filter
    response = await client.get(
        "/api/v1/media/media_csv_filter/comments?status=1",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    payload = response.json()["payload"]
    assert len(payload) == 1


@pytest.mark.asyncio
async def test_media_comments_filter_invalid_status(integration_environment):
    """Test filtering comments with invalid status returns error."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_invalid_filter",
            permalink="https://instagram.com/p/media_invalid_filter",
            media_type="IMAGE",
            media_url="https://cdn.test/invalid.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        await session.commit()

    response = await client.get(
        "/api/v1/media/media_invalid_filter/comments?status=999",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 400
    data = response.json()
    assert data["meta"]["error"]["code"] == 4006


@pytest.mark.asyncio
async def test_media_comments_pagination(integration_environment):
    """Test comment listing pagination."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_comment_pagination",
            permalink="https://instagram.com/p/media_comment_pagination",
            media_type="IMAGE",
            media_url="https://cdn.test/pagination.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)

        # Create 50 comments
        for i in range(50):
            comment = InstagramComment(
                id=f"comment_page_{i}",
                media_id=media.id,
                user_id=f"user_{i}",
                username=f"user{i}",
                text=f"Comment {i}",
                created_at=now_db_utc(),
                raw_data={},
            )
            session.add(comment)
        await session.commit()

    # Default pagination
    response = await client.get(
        "/api/v1/media/media_comment_pagination/comments",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["per_page"] == 30  # Default for comments
    assert data["meta"]["total"] >= 50
    assert len(data["payload"]) == 30

    # Custom per_page
    response = await client.get(
        "/api/v1/media/media_comment_pagination/comments?per_page=10",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["per_page"] == 10
    assert len(data["payload"]) == 10


# ===== Answer Listing Tests =====


@pytest.mark.asyncio
async def test_list_answers_for_comment(integration_environment):
    """Test listing answers for a comment."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_answer_list",
            permalink="https://instagram.com/p/media_answer_list",
            media_type="IMAGE",
            media_url="https://cdn.test/answer_list.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        comment = InstagramComment(
            id="comment_with_answer",
            media_id=media.id,
            user_id="user",
            username="tester",
            text="Question?",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        answer = QuestionAnswer(
            comment_id=comment.id,
            answer="Here is the answer",
            answer_confidence=0.9,
            answer_quality_score=85,
            reply_sent=False,
            processing_status="COMPLETED",
        )
        session.add(answer)
        await session.commit()

    response = await client.get(
        "/api/v1/comments/comment_with_answer/answers",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    payload = response.json()["payload"]
    assert len(payload) == 1
    assert payload[0]["answer"] == "Here is the answer"


@pytest.mark.asyncio
async def test_list_answers_empty(integration_environment):
    """Test listing answers for comment without answers."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_no_answer",
            permalink="https://instagram.com/p/media_no_answer",
            media_type="IMAGE",
            media_url="https://cdn.test/no_answer.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        comment = InstagramComment(
            id="comment_no_answer",
            media_id=media.id,
            user_id="user",
            username="tester",
            text="No answer yet",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        await session.commit()

    response = await client.get(
        "/api/v1/comments/comment_no_answer/answers",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    payload = response.json()["payload"]
    assert len(payload) == 0


# ===== Classification Edge Cases =====


@pytest.mark.asyncio
async def test_patch_classification_invalid_type(integration_environment):
    """Test patching classification with invalid type."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_invalid_class",
            permalink="https://instagram.com/p/media_invalid_class",
            media_type="IMAGE",
            media_url="https://cdn.test/invalid_class.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        comment = InstagramComment(
            id="comment_invalid_class",
            media_id=media.id,
            user_id="user",
            username="tester",
            text="Test",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        await session.commit()

    response = await client.patch(
        "/api/v1/comments/comment_invalid_class/classification",
        headers=auth_headers(integration_environment),
        json={"type": "invalid_classification_type", "reasoning": "test"},
    )
    assert response.status_code == 400
    data = response.json()
    assert data["meta"]["error"]["code"] == 4009


@pytest.mark.asyncio
async def test_patch_classification_creates_if_missing(integration_environment):
    """Test patching classification creates new record if missing."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_create_class",
            permalink="https://instagram.com/p/media_create_class",
            media_type="IMAGE",
            media_url="https://cdn.test/create_class.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        comment = InstagramComment(
            id="comment_create_class",
            media_id=media.id,
            user_id="user",
            username="tester",
            text="New classification",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        await session.commit()

    response = await client.patch(
        "/api/v1/comments/comment_create_class/classification",
        headers=auth_headers(integration_environment),
        json={"type": "question / inquiry", "reasoning": "manual"},
    )
    assert response.status_code == 200
    payload = response.json()["payload"]
    assert payload["classification"]["type"] == 4  # question / inquiry
    assert payload["classification"]["reasoning"] == "manual"
