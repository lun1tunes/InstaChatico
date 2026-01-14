"""Integration tests for OAuth encrypted token ingestion."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from core.config import settings
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
    async with session_factory() as session:
        repo = OAuthTokenRepository(session)
        await repo.upsert(
            provider="instagram",
            account_id=account_id,
            access_token_encrypted="enc-access",
            refresh_token_encrypted=None,
            token_type=None,
            scope=None,
            access_token_expires_at=None,
            refresh_token_expires_at=None,
        )
        await session.commit()

    headers = _internal_jwt_headers(settings.app_secret)
    payload = {"provider": "instagram", "account_id": account_id}
    resp = await client.request("DELETE", "/api/v1/oauth/tokens", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text

    async with session_factory() as session:
        repo = OAuthTokenRepository(session)
        record = await repo.get_by_provider_account("instagram", account_id)
        assert record is None
