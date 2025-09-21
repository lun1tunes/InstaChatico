from pydantic import BaseModel, ConfigDict, Field

class WebhookVerification(BaseModel):
    hub_mode: str
    hub_challenge: str
    hub_verify_token: str

class CommentAuthor(BaseModel):
    id: str
    username: str

class CommentMedia(BaseModel):
    id: str
    media_product_type: str | None = None

class CommentValue(BaseModel):
    from_: CommentAuthor = Field(alias="from")
    media: CommentMedia
    id: str
    parent_id: str | None = None
    text: str

class CommentChange(BaseModel):
    field: str
    value: CommentValue

class WebhookEntry(BaseModel):
    id: str
    time: int
    changes: list[CommentChange]

class WebhookPayload(BaseModel):
    entry: list[WebhookEntry]
    object: str