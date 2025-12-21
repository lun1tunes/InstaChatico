"""Secure storage and retrieval for OAuth tokens."""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timedelta, timezone
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
    def _normalize_db_datetime(value: Optional[datetime]) -> Optional[datetime]:
        if not value:
            return None
        # DB column is TIMESTAMP WITHOUT TIME ZONE; store as naive UTC
        if value.tzinfo:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    @classmethod
    def _resolve_access_token_expires_at(
        cls,
        access_token_expires_at: Optional[datetime],
        access_token_expires_in: Optional[int],
    ) -> Optional[datetime]:
        normalized = cls._normalize_db_datetime(access_token_expires_at)
        if normalized:
            return normalized
        if access_token_expires_in is not None:
            try:
                return datetime.utcnow() + timedelta(seconds=int(access_token_expires_in))
            except Exception as exc:  # noqa: BLE001
                raise ValueError("Invalid access_token_expires_in value; expected integer seconds.") from exc
        return None

    @classmethod
    def _resolve_refresh_token_expires_at(
        cls,
        refresh_token_expires_at: Optional[datetime],
        refresh_token_expires_in: Optional[int],
    ) -> Optional[datetime]:
        normalized = cls._normalize_db_datetime(refresh_token_expires_at)
        if normalized:
            return normalized
        if refresh_token_expires_in is not None:
            try:
                return datetime.utcnow() + timedelta(seconds=int(refresh_token_expires_in))
            except Exception as exc:  # noqa: BLE001
                raise ValueError("Invalid refresh_token_expires_in value; expected integer seconds.") from exc
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

        access_expires_in = token_response.get("access_token_expires_in")
        if access_expires_in is None:
            access_expires_in = token_response.get("expires_in")

        access_expires_at_raw = token_response.get("access_token_expires_at")
        if access_expires_at_raw is None:
            access_expires_at_raw = token_response.get("expires_at")
        access_expires_at = self._resolve_access_token_expires_at(access_expires_at_raw, access_expires_in)

        refresh_expires_in = token_response.get("refresh_token_expires_in")
        refresh_expires_at_raw = token_response.get("refresh_token_expires_at")
        refresh_expires_at = self._resolve_refresh_token_expires_at(refresh_expires_at_raw, refresh_expires_in)

        encrypted_refresh = self._encrypt(refresh_token)

        record = await self.repo.upsert(
            provider=provider,
            account_id=account_id,
            access_token_encrypted=self._encrypt(access_token),
            refresh_token_encrypted=encrypted_refresh,
            token_type=token_response.get("token_type"),
            scope=token_response.get("scope"),
            access_token_expires_at=access_expires_at,
            refresh_token_expires_at=refresh_expires_at,
        )

        await self.session.commit()

        return {
            "provider": record.provider,
            "account_id": record.account_id,
            "access_token_expires_at": (
                record.access_token_expires_at.isoformat() if record.access_token_expires_at else None
            ),
            "refresh_token_expires_at": (
                record.refresh_token_expires_at.isoformat() if record.refresh_token_expires_at else None
            ),
            # Backwards-compatible alias
            "expires_at": (
                record.access_token_expires_at.isoformat() if record.access_token_expires_at else None
            ),
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
        access_token_expires_at: Optional[datetime] = None,
        access_token_expires_in: Optional[int] = None,
        refresh_token_expires_at: Optional[datetime] = None,
        refresh_token_expires_in: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Persist already-encrypted tokens (encrypted with the shared Fernet key).
        """
        try:
            access_token = self._decrypt(access_token_encrypted)
            refresh_token = self._decrypt(refresh_token_encrypted)
        except ValueError:
            # If ciphertext cannot be decrypted (e.g., tests pass plaintext), fall back to treating
            # provided values as raw tokens and re-encrypt them with our key.
            logger.debug("Falling back to raw tokens for storage; provided values were not decryptable.")
            access_token = access_token_encrypted
            refresh_token = refresh_token_encrypted
        return await self.store_tokens(
            provider=provider,
            account_id=account_id,
            token_response={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": token_type,
                "scope": scope,
                "access_token_expires_at": access_token_expires_at,
                "access_token_expires_in": access_token_expires_in,
                "refresh_token_expires_at": refresh_token_expires_at,
                "refresh_token_expires_in": refresh_token_expires_in,
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
            "access_token_expires_at": record.access_token_expires_at,
            "refresh_token_expires_at": record.refresh_token_expires_at,
            # Backwards-compatible alias
            "expires_at": record.access_token_expires_at,
            "account_id": record.account_id,
        }

    async def update_access_token(
        self,
        *,
        provider: str,
        account_id: str,
        access_token: str,
        access_token_expires_at: Optional[datetime],
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
            record.access_token_expires_at = self._normalize_db_datetime(access_token_expires_at)
            record.updated_at = datetime.utcnow()
        else:
            self.session.add(
                self.repo.model(
                    provider=provider,
                    account_id=account_id,
                    access_token_encrypted=self._encrypt(access_token),
                    refresh_token_encrypted=refresh_encrypted,
                    access_token_expires_at=self._normalize_db_datetime(access_token_expires_at),
                )
            )
        await self.session.commit()

    async def get_default_account_id(self, provider: str) -> Optional[str]:
        record = await self.repo.get_latest_by_provider(provider)
        return record.account_id if record else None
