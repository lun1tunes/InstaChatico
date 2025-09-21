from pydantic import BaseModel, ConfigDict, Field

class WebhookVerification(BaseModel):
    hub_mode: str
    hub_challenge: str
    hub_verify_token: str

class CommentAuthor(BaseModel):
    id: int
    username: str

class CommentMedia(BaseModel):
    id: int
    media_product_type: str

class CommentValue(BaseModel):
    from_: CommentAuthor = Field(alias="from")
    media: CommentMedia
    id: int
    parent_id: int | None
    text: str

class CommentChange(BaseModel):
    field: str
    value: CommentValue

class WebhookEntry(BaseModel):
    id: int
    time: int
    changes: list[CommentChange]

class WebhookPayload(BaseModel):
    entry: list[WebhookEntry]
    object: str