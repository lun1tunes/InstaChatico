from pydantic import BaseModel
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
    account_id: Optional[str] = None
    access_token_encrypted: str
    refresh_token_encrypted: str
    token_type: Optional[str] = None
    scope: Optional[Union[str, List[str]]] = None
    expires_at: Optional[datetime] = None
    expires_in: Optional[int] = None


class TokenStoreResponse(BaseModel):
    status: str = "ok"
    provider: str
    account_id: str
    expires_at: Optional[str] = None
    scope: Optional[str] = None
    token_type: Optional[str] = None
    has_refresh_token: bool
