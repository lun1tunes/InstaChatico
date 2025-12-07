"""Secure storage and retrieval for OAuth tokens."""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timedelta
from typing import Optional, Callable, Dict, Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.ext.asyncio import AsyncSession

from core.repositories.oauth_token import OAuthTokenRepository

logger = logging.getLogger(__name__)


class OAuthTokenService:
    """Handles encryption at rest and persistence of OAuth tokens."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        repository_factory: Callable[..., OAuthTokenRepository],
        encryption_key: str,
    ):
        self.session = session
        self.repo = repository_factory(session=session)
        self._fernet = self._build_fernet(encryption_key)

    @staticmethod
    def _build_fernet(key: str) -> Fernet:
        try:
            # Accept both raw key and base64-encoded key
            raw = key.encode("utf-8")
            # Validate base64 format; Fernet expects 32 urlsafe base64 bytes
            base64.urlsafe_b64decode(raw)
            return Fernet(raw)
        except Exception as exc:  # noqa: BLE001
            raise ValueError("Invalid OAUTH_ENCRYPTION_KEY. Expected urlsafe base64 32 bytes.") from exc

    def _encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def _decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Stored OAuth token cannot be decrypted. Check encryption key.") from exc

    @staticmethod
    def _resolve_expires_at(expires_at: Optional[datetime], expires_in: Optional[int]) -> Optional[datetime]:
        if expires_at:
            return expires_at
        if expires_in:
            try:
                return datetime.utcnow() + timedelta(seconds=int(expires_in))
            except Exception as exc:  # noqa: BLE001
                raise ValueError("Invalid expires_in value; expected integer seconds.") from exc
        return None

    async def store_tokens(
        self,
        *,
        provider: str,
        account_id: str,
        token_response: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Persist tokens securely.

        token_response is expected to include:
        - access_token
        - refresh_token
        - expires_in (seconds)
        - token_type
        - scope (space-delimited)
        """
        access_token = token_response.get("access_token")
        refresh_token = token_response.get("refresh_token")
        if not access_token or not refresh_token:
            raise ValueError("Token response missing access_token or refresh_token")

        expires_in = token_response.get("expires_in")
        expires_at = self._resolve_expires_at(token_response.get("expires_at"), expires_in)

        encrypted_refresh = self._encrypt(refresh_token)

        record = await self.repo.upsert(
            provider=provider,
            account_id=account_id,
            access_token_encrypted=self._encrypt(access_token),
            refresh_token_encrypted=encrypted_refresh,
            token_type=token_response.get("token_type"),
            scope=token_response.get("scope"),
            expires_at=expires_at,
        )

        await self.session.commit()

        return {
            "provider": record.provider,
            "account_id": record.account_id,
            "expires_at": record.expires_at.isoformat() if record.expires_at else None,
            "scope": record.scope,
            "token_type": record.token_type,
            "has_refresh_token": True,
        }

    async def store_encrypted_tokens(
        self,
        *,
        provider: str,
        account_id: str,
        access_token_encrypted: str,
        refresh_token_encrypted: str,
        token_type: Optional[str] = None,
        scope: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        expires_in: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Persist already-encrypted tokens (encrypted with the shared Fernet key).
        """
        access_token = self._decrypt(access_token_encrypted)
        refresh_token = self._decrypt(refresh_token_encrypted)
        return await self.store_tokens(
            provider=provider,
            account_id=account_id,
            token_response={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": token_type,
                "scope": scope,
                "expires_at": expires_at,
                "expires_in": expires_in,
            },
        )

    async def get_tokens(self, provider: str, account_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        record = None
        if account_id:
            record = await self.repo.get_by_provider_account(provider, account_id)
        if not record:
            record = await self.repo.get_latest_by_provider(provider)
        if not record:
            return None

        return {
            "access_token": self._decrypt(record.access_token_encrypted),
            "refresh_token": self._decrypt(record.refresh_token_encrypted),
            "token_type": record.token_type,
            "scope": record.scope,
            "expires_at": record.expires_at,
            "account_id": record.account_id,
        }

    async def update_access_token(
        self,
        *,
        provider: str,
        account_id: str,
        access_token: str,
        expires_at: Optional[datetime],
        refresh_token: Optional[str] = None,
    ) -> None:
        """
        Update access token (and optionally refresh token) after refresh.
        """
        record = await self.repo.get_by_provider_account(provider, account_id)
        if not record and not refresh_token:
            # Without refresh token we cannot create a new record safely
            raise ValueError("No existing token found; refresh token required to create a new record.")

        refresh_encrypted = (
            self._encrypt(refresh_token) if refresh_token else (record.refresh_token_encrypted if record else None)
        )
        if not refresh_encrypted:
            raise ValueError("Missing refresh token for persistence.")

        if record:
            record.access_token_encrypted = self._encrypt(access_token)
            record.refresh_token_encrypted = refresh_encrypted
            record.expires_at = expires_at
            record.updated_at = datetime.utcnow()
        else:
            self.session.add(
                self.repo.model(
                    provider=provider,
                    account_id=account_id,
                    access_token_encrypted=self._encrypt(access_token),
                    refresh_token_encrypted=refresh_encrypted,
                    expires_at=expires_at,
                )
            )
        await self.session.commit()

    async def get_default_account_id(self, provider: str) -> Optional[str]:
        record = await self.repo.get_latest_by_provider(provider)
        return record.account_id if record else None
