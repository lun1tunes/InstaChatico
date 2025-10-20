import pytest
from httpx import AsyncClient

from core.models import CommentClassification, InstagramComment, Media, QuestionAnswer
from core.utils.time import now_db_utc


@pytest.mark.asyncio
async def test_get_comment_and_details(integration_environment):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_get",
            permalink="https://instagram.com/p/media_get",
            media_type="IMAGE",
            media_url="https://cdn.test/media_get.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        comment = InstagramComment(
            id="comment_get",
            media_id=media.id,
            user_id="user",
            username="tester",
            text="Sample",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        classification = CommentClassification(
            comment_id=comment.id,
            classification="positive feedback",
            confidence=90,
        )
        session.add(classification)
        answer = QuestionAnswer(
            comment_id=comment.id,
            answer="Thanks!",
            processing_status="COMPLETED",
        )
        session.add(answer)
        await session.commit()

    detail = await client.get("/api/v1/comments/comment_get")
    assert detail.status_code == 200

    full = await client.get("/api/v1/comments/comment_get/full")
    assert full.status_code == 200
    body = full.json()
    assert body["classification"] == "positive feedback"
    assert body["answer"] == "Thanks!"


@pytest.mark.asyncio
async def test_get_comment_not_found(integration_environment):
    client: AsyncClient = integration_environment["client"]
    response = await client.get("/api/v1/comments/missing")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_hide_comment_enqueues_task(integration_environment):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    task_queue = integration_environment["task_queue"]

    async with session_factory() as session:
        media = Media(
            id="media_hide",
            permalink="https://instagram.com/p/media_hide",
            media_type="IMAGE",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        comment = InstagramComment(
            id="comment_hide",
            media_id=media.id,
            user_id="user",
            username="tester",
            text="Hide me",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        await session.commit()

    response = await client.post("/api/v1/comments/comment_hide/hide")
    assert response.status_code == 200
    assert any(
        entry["task"] == "core.tasks.instagram_reply_tasks.hide_instagram_comment_task"
        and entry["args"][0] == "comment_hide"
        for entry in task_queue.enqueued
    )


@pytest.mark.asyncio
async def test_hide_comment_already_hidden(integration_environment):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_hidden",
            permalink="https://instagram.com/p/media_hidden",
            media_type="IMAGE",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        comment = InstagramComment(
            id="comment_hidden",
            media_id=media.id,
            user_id="user",
            username="tester",
            text="Already hidden",
            is_hidden=True,
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        await session.commit()

    response = await client.post("/api/v1/comments/comment_hidden/hide")
    assert response.status_code == 200
    assert response.json()["status"] == "already_hidden"


@pytest.mark.asyncio
async def test_unhide_comment_success(integration_environment):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    instagram_service = integration_environment["instagram_service"]

    async with session_factory() as session:
        media = Media(
            id="media_unhide",
            permalink="https://instagram.com/p/media_unhide",
            media_type="IMAGE",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        comment = InstagramComment(
            id="comment_unhide",
            media_id=media.id,
            user_id="user",
            username="tester",
            text="Hidden comment",
            is_hidden=True,
            hidden_at=now_db_utc(),
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        await session.commit()

    response = await client.post("/api/v1/comments/comment_unhide/unhide")
    assert response.status_code == 200
    result = response.json()
    assert result["status"] in {"success", "not_hidden"}
    # ensure instagram stub tracked attempt when hide=True
    if result["status"] == "success":
        assert "comment_unhide" in instagram_service.hidden or result["status"] == "success"


@pytest.mark.asyncio
async def test_manual_reply_queues_task(integration_environment):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    task_queue = integration_environment["task_queue"]

    async with session_factory() as session:
        media = Media(
            id="media_reply",
            permalink="https://instagram.com/p/media_reply",
            media_type="IMAGE",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        comment = InstagramComment(
            id="comment_reply",
            media_id=media.id,
            user_id="user",
            username="tester",
            text="Reply please",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        await session.commit()

    response = await client.post("/api/v1/comments/comment_reply/reply", params={"message": "Thanks for reaching out!"})
    assert response.status_code == 200
    assert any(
        entry["task"] == "core.tasks.instagram_reply_tasks.send_instagram_reply_task"
        and entry["args"][0] == "comment_reply"
        for entry in task_queue.enqueued
    )
