"""Unit tests for OAuth token ingestion view helpers."""

from __future__ import annotations

import pytest

from api_v1.oauth.views import _store_tokens_impl
from api_v1.oauth.schemas import EncryptedTokenPayload
from core.config import settings


class _FakeOAuthService:
    def __init__(self):
        self.captured_kwargs = {}

    async def store_encrypted_tokens(self, **kwargs):
        self.captured_kwargs = kwargs
        # Minimal successful response shape
        return {
            "provider": kwargs["provider"],
            "account_id": kwargs["account_id"],
            "instagram_user_id": kwargs.get("instagram_user_id"),
            "username": kwargs.get("username"),
            "access_token_expires_at": None,
            "refresh_token_expires_at": None,
            "expires_at": None,
            "scope": kwargs.get("scope"),
            "token_type": kwargs.get("token_type"),
            "has_refresh_token": bool(kwargs.get("refresh_token_encrypted")),
        }


class _FakeContainer:
    def __init__(self, service: _FakeOAuthService):
        self._service = service

    def oauth_token_service(self, session=None):
        return self._service


@pytest.mark.asyncio
async def test_store_tokens_impl_prefers_new_zero_expires_field():
    """Ensure `access_token_expires_in=0` is forwarded without falling back to legacy expires_in."""
    payload = EncryptedTokenPayload(
        provider="youtube",
        account_id="acc-123",
        access_token_encrypted="enc_access",
        refresh_token_encrypted="enc_refresh",
        access_token_expires_in=0,  # falsy but valid
        expires_in=9999,  # legacy field that must NOT override zero
    )

    service = _FakeOAuthService()
    container = _FakeContainer(service)

    result = await _store_tokens_impl(
        payload=payload,
        session=object(),
        container=container,
        x_internal_secret=settings.app_secret,
        authorization=None,
    )

    assert result["status"] == "ok"
    assert service.captured_kwargs["access_token_expires_in"] == 0
    # Backward-compatible alias should reflect what service returned
    assert result["expires_at"] == result["access_token_expires_at"]


@pytest.mark.asyncio
async def test_store_tokens_impl_allows_instagram_without_refresh_token():
    payload = EncryptedTokenPayload(
        provider="instagram",
        account_id="ig-123",
        instagram_user_id="ig-user-123",
        username="ig-user",
        access_token_encrypted="enc_access",
        refresh_token_encrypted=None,
        token_type="bearer",
        scope="instagram_basic",
    )

    service = _FakeOAuthService()
    container = _FakeContainer(service)

    result = await _store_tokens_impl(
        payload=payload,
        session=object(),
        container=container,
        x_internal_secret=settings.app_secret,
        authorization=None,
    )

    assert result["status"] == "ok"
    assert result["provider"] == "instagram"
    assert result["has_refresh_token"] is False
    assert service.captured_kwargs["provider"] == "instagram"
    assert service.captured_kwargs["instagram_user_id"] == "ig-user-123"
    assert service.captured_kwargs["username"] == "ig-user"
    assert service.captured_kwargs["refresh_token_encrypted"] is None
