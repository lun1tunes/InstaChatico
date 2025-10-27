"""Pydantic schemas for the JSON API contract."""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field, model_validator


class MediaUpdateRequest(BaseModel):
    context: Optional[str] = Field(default=None, description="Override AI description of the post")
    is_comment_enabled: Optional[bool] = Field(default=None, description="Allow or disallow new comments")
    is_processing_enabled: Optional[bool] = Field(default=None, description="Toggle automated processing")

    @model_validator(mode="after")
    def at_least_one_field(self) -> "MediaUpdateRequest":
        if all(
            value is None
            for value in (
                self.context,
                self.is_comment_enabled,
                self.is_processing_enabled,
            )
        ):
            raise ValueError("At least one field must be provided")
        return self


class ClassificationUpdateRequest(BaseModel):
    type: str = Field(..., description="Classification label/string")
    reasoning: str = Field(..., description="Manual reasoning for the change")

    @model_validator(mode="after")
    def ensure_reasoning(self) -> "ClassificationUpdateRequest":
        if not self.reasoning.strip():
            raise ValueError("Reasoning cannot be empty")
        return self


class AnswerUpdateRequest(BaseModel):
    answer: str = Field(..., description="Updated answer text")
    quality_score: Optional[int] = Field(default=None, ge=0, le=100)
    confidence: Optional[int] = Field(default=None, ge=0, le=100, description="Confidence in integer percent")


class ErrorDetail(BaseModel):
    code: int
    message: str
    details: Optional[Any] = None


class SimpleMeta(BaseModel):
    error: Optional[ErrorDetail] = None


class PaginationMeta(SimpleMeta):
    page: int
    per_page: int
    total: int


class MediaDTO(BaseModel):
    id: str
    permalink: Optional[str] = None
    caption: Optional[str] = None
    url: Optional[str] = None
    type: Optional[int] = None
    context: Optional[str] = None
    children_urls: list[str] = Field(default_factory=list)
    comments_count: Optional[int] = None
    like_count: Optional[int] = None
    shortcode: Optional[str] = None
    posted_at: Optional[str] = None
    is_comment_enabled: Optional[bool] = None
    is_processing_enabled: bool


class ClassificationDTO(BaseModel):
    id: Optional[int] = None
    processing_status: Optional[int] = None
    processing_completed_at: Optional[str] = None
    last_error: Optional[str] = None
    confidence: Optional[int] = None
    classification_type: Optional[int] = None
    reasoning: Optional[str] = None


class AnswerDTO(BaseModel):
    id: int
    processing_status: Optional[int] = None
    processing_completed_at: Optional[str] = None
    last_error: Optional[str] = None
    answer: Optional[str] = None
    confidence: Optional[int] = None
    quality_score: Optional[int] = None
    reply_sent: bool
    reply_status: Optional[str] = None
    reply_error: Optional[str] = None
    author: Optional[str] = None


class CommentDTO(BaseModel):
    id: str
    parent_id: Optional[str] = None
    username: str
    text: str
    created_at: Optional[str] = None
    is_hidden: bool
    is_deleted: bool
    last_error: Optional[str] = None
    classification: Optional[ClassificationDTO] = None
    answers: list[AnswerDTO] = Field(default_factory=list)


class MediaListResponse(BaseModel):
    meta: PaginationMeta
    payload: list[MediaDTO]


class MediaResponse(BaseModel):
    meta: SimpleMeta
    payload: MediaDTO


class CommentListResponse(BaseModel):
    meta: PaginationMeta
    payload: list[CommentDTO]


class CommentResponse(BaseModel):
    meta: SimpleMeta
    payload: CommentDTO


class AnswerListResponse(BaseModel):
    meta: SimpleMeta
    payload: list[AnswerDTO]


class AnswerResponse(BaseModel):
    meta: SimpleMeta
    payload: AnswerDTO


class ClassificationTypeDTO(BaseModel):
    code: int
    label: str


class ClassificationTypesResponse(BaseModel):
    meta: SimpleMeta
    payload: list[ClassificationTypeDTO]


class EmptyResponse(BaseModel):
    meta: SimpleMeta
    payload: None = None


class ErrorResponse(BaseModel):
    meta: SimpleMeta
    payload: None = None
