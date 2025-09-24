"""
Pydantic v2 schemas for webhook API endpoints.
All request/response models for webhook handling.
"""

from typing import Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, field_validator


class WebhookVerificationParams(BaseModel):
    """Parameters for webhook verification from Instagram"""
    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True
    )
    
    hub_mode: str = Field(alias="hub.mode", description="Webhook mode")
    hub_challenge: str = Field(alias="hub.challenge", description="Challenge string")
    hub_verify_token: str = Field(alias="hub.verify_token", description="Verification token")
    
    @field_validator('hub_mode')
    @classmethod
    def validate_hub_mode(cls, v):
        if v != "subscribe":
            raise ValueError("Only 'subscribe' mode is supported")
        return v


class CommentAuthor(BaseModel):
    """Instagram user who made the comment"""
    model_config = ConfigDict(extra='ignore')
    
    id: str = Field(description="Instagram user ID")
    username: str = Field(description="Instagram username")


class CommentMedia(BaseModel):
    """Instagram media where comment was made"""
    model_config = ConfigDict(extra='ignore')
    
    id: str = Field(description="Instagram media ID")
    media_product_type: str | None = Field(
        default=None, 
        description="Type of media (FEED, STORY, REEL)"
    )


class CommentValue(BaseModel):
    """Comment data from Instagram webhook"""
    model_config = ConfigDict(
        populate_by_name=True,
        extra='ignore'
    )
    
    id: str = Field(description="Instagram comment ID")
    text: str = Field(description="Comment text content", min_length=1)
    from_: CommentAuthor = Field(alias="from", description="Comment author")
    media: CommentMedia = Field(description="Media where comment was made")
    parent_id: str | None = Field(
        default=None, 
        description="Parent comment ID if this is a reply"
    )
    
    @field_validator('text')
    @classmethod
    def validate_text_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Comment text cannot be empty")
        return v.strip()


class CommentChange(BaseModel):
    """Webhook change information"""
    model_config = ConfigDict(extra='ignore')
    
    field: str = Field(description="Changed field name")
    value: CommentValue = Field(description="Comment data")
    
    @field_validator('field')
    @classmethod
    def validate_supported_field(cls, v):
        supported_fields = ["comments", "live_comments"]
        if v not in supported_fields:
            raise ValueError(f"Unsupported field: {v}")
        return v


class WebhookEntry(BaseModel):
    """Webhook entry containing changes"""
    model_config = ConfigDict(extra='ignore')
    
    id: str = Field(description="Instagram page/account ID")
    time: int = Field(description="Unix timestamp of event", gt=0)
    changes: List[CommentChange] = Field(
        description="List of changes",
        min_length=1
    )


class WebhookPayload(BaseModel):
    """Complete webhook payload from Instagram"""
    model_config = ConfigDict(extra='ignore')
    
    object: str = Field(description="Object type")
    entry: List[WebhookEntry] = Field(
        description="List of entries",
        min_length=1
    )
    
    @field_validator('object')
    @classmethod
    def validate_object_type(cls, v):
        if v != "instagram":
            raise ValueError(f"Unsupported object type: {v}")
        return v


# Response schemas
class WebhookProcessingResult(BaseModel):
    """Result of webhook processing"""
    model_config = ConfigDict()
    
    status: str = Field(description="Processing status")
    processed: int = Field(ge=0, description="Number of comments processed")
    skipped: int = Field(ge=0, description="Number of comments skipped")
    errors: int = Field(ge=0, description="Number of processing errors")
    message: str | None = Field(default=None, description="Additional message")
    processing_time_ms: int | None = Field(
        default=None,
        ge=0,
        description="Total processing time in milliseconds"
    )


class CommentProcessingStatus(BaseModel):
    """Status of individual comment processing"""
    model_config = ConfigDict()
    
    comment_id: str = Field(description="Instagram comment ID")
    status: str = Field(description="Processing status")
    classification: str | None = Field(
        default=None,
        description="AI classification result"
    )
    confidence: int | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Classification confidence"
    )
    error: str | None = Field(default=None, description="Error message if failed")
    processed_at: datetime | None = Field(
        default=None,
        description="When processing completed"
    )


class WebhookHealthStatus(BaseModel):
    """Health status for webhook service"""
    model_config = ConfigDict()
    
    status: str = Field(description="Health status")
    service: str = Field(description="Service name")
    timestamp: datetime = Field(description="Status check timestamp")
    details: Dict[str, Any] | None = Field(
        default=None,
        description="Additional health details"
    )
