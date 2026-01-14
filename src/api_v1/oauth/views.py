"""Google OAuth callback handler for YouTube Data API."""

from __future__ import annotations

import logging
import time
import uuid
import hmac
import hashlib
import urllib.parse
from typing import Any, Dict, Optional

import httpx
import jwt
from fastapi import APIRouter, HTTPException, Query, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.container import get_container, Container
from core.models import db_helper
from core.services.oauth_token_service import OAuthTokenService
from .schemas import (
    AuthUrlResponse,
    AccountStatusResponse,
    EncryptedTokenPayload,
    TokenDeletePayload,
    TokenStoreResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["oauth"])
# Dedicated router for internal token ingest at /oauth/tokens
tokens_router = APIRouter(tags=["oauth"])

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.force-ssl",  # manage and moderate YouTube comments
]

STATE_TTL_SECONDS = 600  # 10 minutes

@router.get("/callback")
async def google_oauth_callback(
    code: str = Query(..., description="Authorization code returned by Google"),
    state: Optional[str] = Query(None, description="Opaque state value returned by Google"),
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
    container: Container = Depends(get_container),
) -> Dict[str, Any]:
    """
    Handle OAuth redirect from Google and exchange authorization code for tokens.

    The authorization server redirects the user's browser back to this endpoint with:
    - `code` (query param): short-lived authorization code
    - `state` (optional): value you supplied in the initial auth request

    This endpoint performs the server-to-server token exchange using the app's
    client credentials and returns the token payload. Credentials are never
    included in the redirect; only the authorization code is present.
    """
    token_endpoint = "https://oauth2.googleapis.com/token"
    payload = {
        "code": code,
        "client_id": settings.youtube.client_id,
        "client_secret": settings.youtube.client_secret,
        "redirect_uri": settings.youtube.redirect_uri,
        "grant_type": "authorization_code",
    }

    logger.info("Exchanging Google OAuth code for tokens | has_state=%s", bool(state))

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(token_endpoint, data=payload)
    except httpx.HTTPError as exc:  # pragma: no cover - network errors
        logger.error("OAuth token exchange request failed | error=%s", exc)
        raise HTTPException(status_code=502, detail="Failed to contact Google token endpoint")

    if response.status_code != 200:
        logger.error(
            "OAuth token exchange failed | status=%s | body=%s",
            response.status_code,
            response.text,
        )
        raise HTTPException(status_code=400, detail="Authorization code exchange failed")

    token_data = response.json()

    if state:
        _validate_state(state)

    oauth_service: OAuthTokenService = container.oauth_token_service(session=session)

    # Fetch channel ID using the fresh access token
    channel_id = await _fetch_channel_id(token_data.get("access_token"))
    account_id = channel_id or settings.youtube.channel_id or "default"

    stored = await oauth_service.store_tokens(
        provider="google",
        account_id=account_id,
        token_response=token_data,
    )

    # Preserve state in response for caller correlation (if provided)
    if state is not None:
        stored["state"] = state

    logger.info(
        "OAuth token exchange succeeded | contains_refresh=%s | account_id=%s",
        "refresh_token" in token_data,
        stored["account_id"],
    )
    return stored


@router.get("/authorize", response_model=AuthUrlResponse)
async def google_oauth_authorize(state: Optional[str] = Query(None)) -> AuthUrlResponse:
    """
    Generate the Google OAuth authorization URL for the frontend to redirect the user.

    This endpoint constructs the consent URL with:
    - response_type=code
    - access_type=offline (so we get refresh tokens)
    - include_granted_scopes=true (incremental auth)
    - prompt=consent (ensure refresh token returned)
    - scope: YouTube comment management
    """
    generated_state = state or _generate_state()

    params = {
        "client_id": settings.youtube.client_id,
        "redirect_uri": settings.youtube.redirect_uri,
        "response_type": "code",
        "scope": " ".join(YOUTUBE_SCOPES),
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": generated_state,
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params, safe=":/ ")
    return AuthUrlResponse(auth_url=auth_url, state=generated_state)


def _generate_state() -> str:
    """
    Generate a signed, time-bound state token to mitigate CSRF.
    Encodes nonce:timestamp:signature with HMAC using APP_SECRET.
    """
    nonce = uuid.uuid4().hex
    ts = str(int(time.time()))
    msg = f"{nonce}:{ts}"
    sig = hmac.new(settings.app_secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return f"{nonce}:{ts}:{sig}"


def _validate_state(state: str) -> None:
    """Validate HMAC state and expiration."""
    try:
        nonce, ts, sig = state.split(":")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    msg = f"{nonce}:{ts}"
    expected_sig = hmac.new(settings.app_secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        raise HTTPException(status_code=400, detail="State verification failed")

    if int(time.time()) - int(ts) > STATE_TTL_SECONDS:
        raise HTTPException(status_code=400, detail="State expired")


async def _fetch_channel_id(access_token: Optional[str]) -> Optional[str]:
    if not access_token:
        return None
    url = "https://www.googleapis.com/youtube/v3/channels"
    params = {"part": "id", "mine": "true"}
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code != 200:
                logger.warning("Failed to fetch channel ID | status=%s | body=%s", resp.status_code, resp.text)
                return None
            data = resp.json()
            items = data.get("items") or []
            if not items:
                return None
            return items[0].get("id")
    except httpx.HTTPError as exc:
        logger.warning("HTTP error while fetching channel ID | error=%s", exc)
        return None


@router.get("/account", response_model=AccountStatusResponse)
async def google_account_status(
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
    container: Container = Depends(get_container),
):
    """Return stored Google account/channel status for UI."""
    oauth_service: OAuthTokenService = container.oauth_token_service(session=session)
    tokens = await oauth_service.get_tokens("google")
    return {
        "has_tokens": bool(tokens),
        "account_id": tokens.get("account_id") if tokens else None,
    }


def _resolve_oauth_provider(provider: str) -> tuple[str, str]:
    normalized = (provider or "").strip().lower()
    if normalized == "youtube":
        return normalized, "google"
    if normalized == "instagram":
        return normalized, "instagram"
    raise HTTPException(status_code=400, detail="provider must be 'youtube' or 'instagram'")


async def _store_tokens_impl(
    payload: EncryptedTokenPayload,
    session: AsyncSession,
    container: Container,
    x_internal_secret: str | None,
    authorization: str | None,
):
    """
    Shared implementation for storing encrypted OAuth tokens.
    """
    _authorize_internal_request(authorization=authorization, x_internal_secret=x_internal_secret)

    provider, storage_provider = _resolve_oauth_provider(payload.provider)
    account_id = (payload.account_id or "").strip()
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id is required")

    instagram_user_id = (payload.instagram_user_id or "").strip()
    username = (payload.username or "").strip()
    if provider == "instagram":
        missing = []
        if not instagram_user_id:
            missing.append("instagram_user_id")
        if not username:
            missing.append("username")
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required fields for instagram: {', '.join(missing)}",
            )

    # Normalize scope to space-delimited string
    scope_value = payload.scope
    if isinstance(scope_value, list):
        scope_value = " ".join(scope_value)
    refresh_token_enc = payload.refresh_token_encrypted
    if provider == "youtube" and not refresh_token_enc:
        raise HTTPException(status_code=400, detail="refresh_token_encrypted is required for offline access")

    oauth_service: OAuthTokenService = container.oauth_token_service(session=session)
    try:
        access_token_expires_at = (
            payload.access_token_expires_at
            if payload.access_token_expires_at is not None
            else payload.expires_at
        )
        access_token_expires_in = (
            payload.access_token_expires_in
            if payload.access_token_expires_in is not None
            else payload.expires_in
        )
        stored = await oauth_service.store_encrypted_tokens(
            provider=storage_provider,
            account_id=account_id,
            instagram_user_id=instagram_user_id or None,
            username=username or None,
            access_token_encrypted=payload.access_token_encrypted,
            refresh_token_encrypted=refresh_token_enc,
            token_type=payload.token_type,
            scope=scope_value,
            access_token_expires_at=access_token_expires_at,
            access_token_expires_in=access_token_expires_in,
            refresh_token_expires_at=payload.refresh_token_expires_at,
            refresh_token_expires_in=payload.refresh_token_expires_in,
        )
        # Ensure refresh token presence for offline access
        if provider == "youtube" and not stored.get("has_refresh_token"):
            raise ValueError("refresh_token is required for offline access")
    except ValueError as exc:
        logger.error("Failed to store encrypted tokens | provider=%s | account_id=%s | error=%s", provider, account_id, exc)
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error storing encrypted tokens | provider=%s | account_id=%s", provider, account_id)
        raise HTTPException(status_code=500, detail="Failed to store tokens") from exc

    return {"status": "ok", **stored}


@router.post("/tokens", response_model=TokenStoreResponse)
async def store_encrypted_tokens(
    payload: EncryptedTokenPayload,
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
    container: Container = Depends(get_container),
    x_internal_secret: str | None = Header(None, alias="X-Internal-Secret"),
    authorization: str | None = Header(None, alias="Authorization"),
):
    """Store encrypted tokens via /auth/google/tokens (existing path)."""
    return await _store_tokens_impl(payload, session, container, x_internal_secret, authorization)


@tokens_router.post("/oauth/tokens", response_model=TokenStoreResponse)
async def store_encrypted_tokens_root(
    payload: EncryptedTokenPayload,
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
    container: Container = Depends(get_container),
    x_internal_secret: str | None = Header(None, alias="X-Internal-Secret"),
    authorization: str | None = Header(None, alias="Authorization"),
):
    """Store encrypted tokens via /oauth/tokens (mapper callback path)."""
    logger.debug(
        "Received internal token sync | has_auth_header=%s | has_internal_header=%s",
        bool(authorization),
        bool(x_internal_secret),
    )
    return await _store_tokens_impl(payload, session, container, x_internal_secret, authorization)


@tokens_router.delete("/oauth/tokens")
async def delete_tokens_root(
    payload: TokenDeletePayload,
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
    container: Container = Depends(get_container),
    x_internal_secret: str | None = Header(None, alias="X-Internal-Secret"),
    authorization: str | None = Header(None, alias="Authorization"),
):
    """Delete stored encrypted tokens via /oauth/tokens (mapper disconnect path)."""
    logger.debug(
        "Received internal token delete | has_auth_header=%s | has_internal_header=%s",
        bool(authorization),
        bool(x_internal_secret),
    )
    _authorize_internal_request(authorization=authorization, x_internal_secret=x_internal_secret)

    provider, storage_provider = _resolve_oauth_provider(payload.provider)
    account_id = (payload.account_id or "").strip()
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id is required")

    logger.info("Internal token delete requested | provider=%s | account_id=%s", provider, account_id)

    oauth_service: OAuthTokenService = container.oauth_token_service(session=session)
    deleted = await oauth_service.delete_tokens(provider=storage_provider, account_id=account_id)

    logger.info(
        "Internal token delete completed | provider=%s | account_id=%s | deleted=%s",
        provider,
        account_id,
        deleted,
    )
    return {"status": "ok", "account_id": account_id, "deleted": deleted}


def _authorize_internal_request(
    *,
    authorization: str | None,
    x_internal_secret: str | None,
) -> None:
    """
    Validate mapper -> worker calls using a short-lived JWT.

    Falls back to legacy X-Internal-Secret for backward compatibility.
    """
    bearer = _extract_bearer_token(authorization)
    if bearer:
        try:
            _validate_internal_jwt(bearer)
            return
        except HTTPException:
            # bubble up after logging context
            logger.warning("Internal JWT validation failed | header_present=%s", bool(authorization))
            raise

    if x_internal_secret and x_internal_secret == settings.app_secret:
        return

    logger.warning(
        "Internal auth failed | has_authorization=%s | has_x_internal=%s",
        bool(authorization),
        bool(x_internal_secret),
    )
    raise HTTPException(status_code=401, detail="Unauthorized")


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        token = parts[1].strip()
        return token or None
    return None


def _validate_internal_jwt(token: str) -> Dict[str, Any]:
    """
    Validate internal JWT issued by the mapper app.
    """
    try:
        payload = jwt.decode(
            token,
            settings.app_secret,
            algorithms=["HS256"],
            audience="instagram-worker",
            options={"require": ["exp", "iat", "iss", "aud"]},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Internal token validation failed: %s", exc)
        raise HTTPException(status_code=401, detail="Unauthorized") from exc

    if payload.get("iss") != "chatico-mapper":
        raise HTTPException(status_code=401, detail="Unauthorized")

    raw_scope = payload.get("scope")
    if raw_scope is None:
        raw_scope = payload.get("scopes")

    scopes: list[str] = []
    if isinstance(raw_scope, str):
        scopes = [part.strip().lower() for part in raw_scope.replace(",", " ").split() if part.strip()]
    elif isinstance(raw_scope, (list, tuple, set)):
        scopes = [str(item).strip().lower() for item in raw_scope if str(item).strip()]

    if "internal" not in scopes:
        raise HTTPException(status_code=401, detail="Unauthorized")

    return payload
