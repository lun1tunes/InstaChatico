"""Integration tests for OAuth encrypted token ingestion."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import jwt
import pytest
from sqlalchemy import select

from core.config import settings
from core.models import (
    CommentClassification,
    FollowersDynamic,
    InstagramComment,
    InstrumentTokenUsage,
    Media,
    ModerationStatsReport,
    QuestionAnswer,
    StatsReport,
)
from core.models.comment_classification import ProcessingStatus
from core.models.question_answer import AnswerStatus
from core.repositories.oauth_token import OAuthTokenRepository


@pytest.mark.asyncio
async def test_store_encrypted_tokens_accepts_zero_expiry(integration_environment):
    client = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    headers = {"X-Internal-Secret": "test_app_secret"}

    payload = {
        "provider": "youtube",
        "account_id": "acc-int",
        "access_token_encrypted": "enc-access",
        "refresh_token_encrypted": "enc-refresh",
        "access_token_expires_in": 0,  # must not fall back to legacy field
        "expires_in": 9999,
    }

    resp = await client.post("/api/v1/auth/google/tokens", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    assert body["account_id"] == "acc-int"

    async with session_factory() as session:
        repo = OAuthTokenRepository(session)
        record = await repo.get_by_provider_account("google", "acc-int")
        assert record is not None
        assert record.access_token_expires_at is not None
        assert record.instagram_user_id is None
        assert record.username is None
        # expires_in=0 should set expiry ~now
        assert abs(record.access_token_expires_at - datetime.utcnow()) < timedelta(seconds=2)


def _internal_jwt_headers(secret: str) -> dict[str, str]:
    now = datetime.now(timezone.utc)
    payload = {
        "iss": "chatico-mapper",
        "aud": "instagram-worker",
        "scope": "internal",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
    }
    token = jwt.encode(payload, secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_delete_oauth_tokens_unauthorized_returns_401(integration_environment):
    client = integration_environment["client"]

    payload = {"provider": "youtube", "account_id": "acc-del-unauth"}
    resp = await client.request("DELETE", "/api/v1/oauth/tokens", json=payload)
    assert resp.status_code == 401, resp.text


@pytest.mark.asyncio
async def test_delete_oauth_tokens_authorized_deletes_record(integration_environment):
    client = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    account_id = "acc-del"
    async with session_factory() as session:
        repo = OAuthTokenRepository(session)
        await repo.upsert(
            provider="google",
            account_id=account_id,
            access_token_encrypted="enc-access",
            refresh_token_encrypted="enc-refresh",
            token_type=None,
            scope=None,
            access_token_expires_at=None,
            refresh_token_expires_at=None,
        )
        await session.commit()

    headers = _internal_jwt_headers(settings.app_secret)
    payload = {"provider": "youtube", "account_id": account_id}
    resp = await client.request("DELETE", "/api/v1/oauth/tokens", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text

    async with session_factory() as session:
        repo = OAuthTokenRepository(session)
        record = await repo.get_by_provider_account("google", account_id)
        assert record is None


@pytest.mark.asyncio
async def test_delete_oauth_tokens_is_idempotent(integration_environment):
    client = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    account_id = "acc-del-repeat"
    headers = _internal_jwt_headers(settings.app_secret)
    payload = {"provider": "youtube", "account_id": account_id}

    first = await client.request("DELETE", "/api/v1/oauth/tokens", json=payload, headers=headers)
    assert first.status_code == 200, first.text

    second = await client.request("DELETE", "/api/v1/oauth/tokens", json=payload, headers=headers)
    assert second.status_code == 200, second.text

    async with session_factory() as session:
        repo = OAuthTokenRepository(session)
        record = await repo.get_by_provider_account("google", account_id)
        assert record is None


@pytest.mark.asyncio
async def test_store_instagram_tokens_upserts_record(integration_environment):
    client = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    headers = {"X-Internal-Secret": "test_app_secret"}

    account_id = "ig-acc-1"
    instagram_user_id = "ig-user-1"
    username = "ig-user-handle"
    payload = {
        "provider": "instagram",
        "account_id": account_id,
        "instagram_user_id": instagram_user_id,
        "username": username,
        "access_token_encrypted": "enc-access-1",
        "token_type": "bearer",
        "scope": "instagram_business_basic",
        "access_token_expires_in": 3600,
    }

    resp = await client.post("/api/v1/oauth/tokens", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["provider"] == "instagram"
    assert body["account_id"] == account_id
    assert body["instagram_user_id"] == instagram_user_id
    assert body["username"] == username
    assert body["has_refresh_token"] is False

    async with session_factory() as session:
        repo = OAuthTokenRepository(session)
        record = await repo.get_by_provider_account("instagram", account_id)
        assert record is not None
        assert record.refresh_token_encrypted is None
        assert record.instagram_user_id == instagram_user_id
        assert record.username == username
        first_encrypted = record.access_token_encrypted

    payload["access_token_encrypted"] = "enc-access-2"
    resp = await client.post("/api/v1/oauth/tokens", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text

    async with session_factory() as session:
        repo = OAuthTokenRepository(session)
        record = await repo.get_by_provider_account("instagram", account_id)
        assert record is not None
        assert record.access_token_encrypted != first_encrypted


@pytest.mark.asyncio
async def test_delete_instagram_tokens_authorized_deletes_record(integration_environment):
    client = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    account_id = "ig-del"
    instagram_user_id = "ig-user-del"
    username = "ig-user-handle"
    async with session_factory() as session:
        repo = OAuthTokenRepository(session)
        await repo.upsert(
            provider="instagram",
            account_id=account_id,
            instagram_user_id=instagram_user_id,
            username=username,
            access_token_encrypted="enc-access",
            refresh_token_encrypted=None,
            token_type=None,
            scope=None,
            access_token_expires_at=None,
            refresh_token_expires_at=None,
        )
        await session.commit()

    headers = _internal_jwt_headers(settings.app_secret)
    payload = {
        "provider": "instagram",
        "account_id": account_id,
        "instagram_user_id": instagram_user_id,
        "username": username,
    }
    resp = await client.request("DELETE", "/api/v1/oauth/tokens", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text

    async with session_factory() as session:
        repo = OAuthTokenRepository(session)
        record = await repo.get_by_provider_account("instagram", account_id)
        assert record is None


@pytest.mark.asyncio
async def test_data_deletion_removes_instagram_account_data(integration_environment):
    client = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    account_id = "ig-account-del"
    other_account_id = "ig-account-keep"
    instagram_user_id = "ig-user-del"
    username = "ig_user_handle"
    other_username = "ig_user_keep"

    async with session_factory() as session:
        repo = OAuthTokenRepository(session)
        await repo.upsert(
            provider="instagram",
            account_id=account_id,
            instagram_user_id=instagram_user_id,
            username=username,
            access_token_encrypted="enc-access",
            refresh_token_encrypted=None,
            token_type=None,
            scope=None,
            access_token_expires_at=None,
            refresh_token_expires_at=None,
        )
        await repo.upsert(
            provider="instagram",
            account_id=other_account_id,
            instagram_user_id="ig-user-keep",
            username=other_username,
            access_token_encrypted="enc-access-2",
            refresh_token_encrypted=None,
            token_type=None,
            scope=None,
            access_token_expires_at=None,
            refresh_token_expires_at=None,
        )

        media_del = Media(
            id="media-del",
            platform="instagram",
            permalink="https://instagram.com/p/media-del",
            caption="Delete me",
            media_url="https://cdn.test/media-del.jpg",
            media_type="IMAGE",
            comments_count=0,
            like_count=0,
            shortcode="short-del",
            is_processing_enabled=True,
            created_at=datetime(2025, 1, 1),
            updated_at=datetime(2025, 1, 1),
            owner=account_id,
            username=username,
        )
        media_keep = Media(
            id="media-keep",
            platform="instagram",
            permalink="https://instagram.com/p/media-keep",
            caption="Keep me",
            media_url="https://cdn.test/media-keep.jpg",
            media_type="IMAGE",
            comments_count=0,
            like_count=0,
            shortcode="short-keep",
            is_processing_enabled=True,
            created_at=datetime(2025, 1, 1),
            updated_at=datetime(2025, 1, 1),
            owner=other_account_id,
            username=other_username,
        )
        session.add_all([media_del, media_keep])

        comment_del = InstagramComment(
            id="comment-del",
            media_id=media_del.id,
            user_id="user-del",
            username="commenter",
            text="delete comment",
            created_at=datetime.utcnow(),
            raw_data={},
        )
        comment_keep = InstagramComment(
            id="comment-keep",
            media_id=media_keep.id,
            user_id="user-keep",
            username="commenter2",
            text="keep comment",
            created_at=datetime.utcnow(),
            raw_data={},
        )
        session.add_all([comment_del, comment_keep])

        classification_del = CommentClassification(
            comment_id=comment_del.id,
            processing_status=ProcessingStatus.COMPLETED,
        )
        answer_del = QuestionAnswer(
            comment_id=comment_del.id,
            processing_status=AnswerStatus.COMPLETED,
            answer="ok",
        )
        session.add_all([classification_del, answer_del])

        usage_del = InstrumentTokenUsage(
            tool="test",
            task="classify",
            model="gpt-5",
            tokens_in=1,
            tokens_out=1,
            comment_id=comment_del.id,
            details={},
        )
        usage_keep = InstrumentTokenUsage(
            tool="test",
            task="classify",
            model="gpt-5",
            tokens_in=1,
            tokens_out=1,
            comment_id=comment_keep.id,
            details={},
        )
        session.add_all([usage_del, usage_keep])

        follower_del = FollowersDynamic(
            snapshot_date=date(2025, 1, 1),
            username=username,
            followers_count=10,
            follows_count=5,
            media_count=1,
            raw_payload={},
        )
        follower_keep = FollowersDynamic(
            snapshot_date=date(2025, 1, 2),
            username=other_username,
            followers_count=20,
            follows_count=7,
            media_count=2,
            raw_payload={},
        )
        session.add_all([follower_del, follower_keep])

        stats = StatsReport(
            period_label="2025-01",
            range_start=datetime(2025, 1, 1),
            range_end=datetime(2025, 2, 1),
            payload={"ok": True},
        )
        moderation = ModerationStatsReport(
            period_label="2025-01",
            range_start=datetime(2025, 1, 1),
            range_end=datetime(2025, 2, 1),
            payload={"ok": True},
        )
        session.add_all([stats, moderation])

        await session.commit()

    headers = _internal_jwt_headers(settings.app_secret)
    payload = {
        "provider": "instagram",
        "instagram_user_id": instagram_user_id,
        "account_ids": [account_id],
    }
    resp = await client.post("/api/v1/oauth/data-deletion", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text

    async with session_factory() as session:
        repo = OAuthTokenRepository(session)
        assert await repo.get_by_provider_account("instagram", account_id) is None
        assert await repo.get_by_provider_account("instagram", other_account_id) is not None

        assert await session.get(Media, media_del.id) is None
        assert await session.get(Media, media_keep.id) is not None

        assert await session.get(InstagramComment, comment_del.id) is None
        assert await session.get(InstagramComment, comment_keep.id) is not None

        classification = await session.execute(
            select(CommentClassification).where(CommentClassification.comment_id == comment_del.id)
        )
        assert classification.scalar_one_or_none() is None

        answer = await session.execute(
            select(QuestionAnswer).where(QuestionAnswer.comment_id == comment_del.id)
        )
        assert answer.scalar_one_or_none() is None

        usage = await session.execute(
            select(InstrumentTokenUsage).where(InstrumentTokenUsage.comment_id == comment_del.id)
        )
        assert usage.scalar_one_or_none() is None

        usage_keep = await session.execute(
            select(InstrumentTokenUsage).where(InstrumentTokenUsage.comment_id == comment_keep.id)
        )
        assert usage_keep.scalar_one_or_none() is not None

        followers = await session.execute(
            select(FollowersDynamic).where(FollowersDynamic.username == username)
        )
        assert followers.scalar_one_or_none() is None

        followers_keep = await session.execute(
            select(FollowersDynamic).where(FollowersDynamic.username == other_username)
        )
        assert followers_keep.scalar_one_or_none() is not None

        stats_rows = (await session.execute(select(StatsReport))).scalars().all()
        moderation_rows = (await session.execute(select(ModerationStatsReport))).scalars().all()
        assert stats_rows == []
        assert moderation_rows == []
