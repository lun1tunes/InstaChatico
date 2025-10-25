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
