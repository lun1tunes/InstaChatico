"""Tests for OAuthTokenService YouTube expiry handling."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.repositories.oauth_token import OAuthTokenRepository
from core.services.oauth_token_service import OAuthTokenService


@pytest.mark.asyncio
async def test_store_tokens_sets_access_and_refresh_expiry(db_session):
    service = OAuthTokenService(
        session=db_session,
        repository_factory=OAuthTokenRepository,
        encryption_key="1p_UUU0j5OJ9SxWwtUWFI7Ak4luuL8EA3twJY86W0Z0=",
    )

    now = datetime.utcnow()
    token_response = {
        "access_token": "access",
        "refresh_token": "refresh",
        "expires_in": 3600,
        "refresh_token_expires_in": 7200,
        "token_type": "Bearer",
        "scope": "scope1",
    }

    stored = await service.store_tokens(provider="google", account_id="acc-1", token_response=token_response)

    # Access expiry should be ~1h from now
    access_at = datetime.fromisoformat(stored["access_token_expires_at"])
    assert timedelta(minutes=50) < access_at - now < timedelta(minutes=70)

    # Refresh expiry should be ~2h from now
    refresh_at = datetime.fromisoformat(stored["refresh_token_expires_at"])
    assert timedelta(minutes=110) < refresh_at - now < timedelta(minutes=130)


@pytest.mark.asyncio
async def test_store_tokens_prefers_explicit_access_expires_at(db_session):
    service = OAuthTokenService(
        session=db_session,
        repository_factory=OAuthTokenRepository,
        encryption_key="1p_UUU0j5OJ9SxWwtUWFI7Ak4luuL8EA3twJY86W0Z0=",
    )

    explicit_at = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    token_response = {
        "access_token": "access2",
        "refresh_token": "refresh2",
        "access_token_expires_at": explicit_at,
        "expires_in": 10,  # should be ignored in favor of explicit_at
        "token_type": "Bearer",
        "scope": "scope2",
    }

    stored = await service.store_tokens(provider="google", account_id="acc-2", token_response=token_response)

    access_at = datetime.fromisoformat(stored["access_token_expires_at"])
    assert access_at == explicit_at.replace(tzinfo=None)  # normalized to naive UTC

    # Legacy alias maintained
    assert stored["expires_at"] == stored["access_token_expires_at"]


@pytest.mark.asyncio
async def test_store_tokens_keeps_zero_access_expires_in(db_session):
    """Ensure falsy-but-valid expires_in=0 is honored instead of falling back."""
    service = OAuthTokenService(
        session=db_session,
        repository_factory=OAuthTokenRepository,
        encryption_key="1p_UUU0j5OJ9SxWwtUWFI7Ak4luuL8EA3twJY86W0Z0=",
    )

    token_response = {
        "access_token": "access3",
        "refresh_token": "refresh3",
        "access_token_expires_in": 0,  # valid value that must not fall back
        "expires_in": 9999,  # legacy field should be ignored because new field is present
        "token_type": "Bearer",
        "scope": "scope3",
    }

    stored = await service.store_tokens(provider="google", account_id="acc-3", token_response=token_response)

    access_at = datetime.fromisoformat(stored["access_token_expires_at"])
    # Should be effectively "now" because expires_in is zero seconds
    assert abs(access_at - datetime.utcnow()) < timedelta(seconds=2)
