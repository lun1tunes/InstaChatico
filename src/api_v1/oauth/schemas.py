from pydantic import BaseModel, Field, model_validator
from datetime import datetime
from typing import Optional, List, Union


class AuthUrlResponse(BaseModel):
    auth_url: str
    state: str


class AccountStatusResponse(BaseModel):
    has_tokens: bool
    account_id: str | None


class EncryptedTokenPayload(BaseModel):
    provider: str
    account_id: str
    instagram_user_id: Optional[str] = None
    username: Optional[str] = None
    access_token_encrypted: str
    refresh_token_encrypted: Optional[str] = None
    token_type: Optional[str] = None
    scope: Optional[Union[str, List[str]]] = None
    # Access token expiry (usually ~1 hour)
    access_token_expires_at: Optional[datetime] = None
    access_token_expires_in: Optional[int] = None
    # Refresh token expiry (usually long-lived; may exist for time-based access)
    refresh_token_expires_at: Optional[datetime] = None
    refresh_token_expires_in: Optional[int] = None
    # Legacy aliases (access token expiry)
    expires_at: Optional[datetime] = None
    expires_in: Optional[int] = None

    @model_validator(mode="after")
    def _validate_instagram_fields(self):
        provider = (self.provider or "").strip().lower()
        if provider == "instagram":
            missing = []
            if not self.account_id.strip():
                missing.append("account_id")
            if not (self.instagram_user_id or "").strip():
                missing.append("instagram_user_id")
            if not (self.username or "").strip():
                missing.append("username")
            if missing:
                raise ValueError(f"Missing required fields for instagram: {', '.join(missing)}")
        return self


class TokenStoreResponse(BaseModel):
    status: str = "ok"
    provider: str
    account_id: str
    instagram_user_id: Optional[str] = None
    username: Optional[str] = None
    access_token_expires_at: Optional[str] = None
    refresh_token_expires_at: Optional[str] = None
    # Legacy alias (access token expiry)
    expires_at: Optional[str] = None
    scope: Optional[str] = None
    token_type: Optional[str] = None
    has_refresh_token: bool


class TokenDeletePayload(BaseModel):
    provider: str
    account_id: str
    instagram_user_id: Optional[str] = None
    username: Optional[str] = None


class DataDeletionPayload(BaseModel):
    provider: str
    instagram_user_id: Optional[str] = None
    account_ids: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_payload(self):
        has_accounts = bool([value for value in self.account_ids if value and value.strip()])
        has_user_id = bool((self.instagram_user_id or "").strip())
        if not has_accounts and not has_user_id:
            raise ValueError("account_ids or instagram_user_id is required")
        return self
