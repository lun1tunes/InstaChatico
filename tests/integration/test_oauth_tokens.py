"""Integration tests for OAuth encrypted token ingestion."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

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
        # expires_in=0 should set expiry ~now
        assert abs(record.access_token_expires_at - datetime.utcnow()) < timedelta(seconds=2)
