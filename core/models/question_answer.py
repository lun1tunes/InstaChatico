from __future__ import annotations
from typing import TYPE_CHECKING
from datetime import datetime
from enum import Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, String, Text, Integer, JSON
from sqlalchemy.dialects.postgresql import ENUM as SQLEnum
from .base import Base

if TYPE_CHECKING:
    from .comment_classification import CommentClassification

class AnswerStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRY = "RETRY"

class QuestionAnswer(Base):
    __tablename__ = "question_messages_answers"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    comment_id: Mapped[str] = mapped_column(
        ForeignKey("comments_classification.comment_id", ondelete="CASCADE"), 
        unique=True, 
        index=True
    )
    
    # Session management
    conversation_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    
    processing_status: Mapped[AnswerStatus] = mapped_column(
        SQLEnum(AnswerStatus, name="answerstatus"),
        default=AnswerStatus.PENDING
    )
    processing_started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    processing_completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    
    retry_count: Mapped[int] = mapped_column(default=0)
    max_retries: Mapped[int] = mapped_column(default=3)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Answer content
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_confidence: Mapped[float | None] = mapped_column(nullable=True)  # 0.0-1.0
    answer_quality_score: Mapped[int | None] = mapped_column(nullable=True)  # 0-100
    
    # LLM metadata
    llm_raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    tokens_used: Mapped[int | None] = mapped_column(nullable=True)
    processing_time_ms: Mapped[int | None] = mapped_column(nullable=True)
    
    # Additional metadata
    meta_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    
    # Instagram reply tracking
    reply_sent: Mapped[bool] = mapped_column(default=False)
    reply_sent_at: Mapped[datetime | None] = mapped_column(nullable=True)
    reply_status: Mapped[str | None] = mapped_column(String(50), nullable=True)  # sent, failed, pending
    reply_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    reply_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reply_id: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Instagram reply ID to prevent infinite loops
    
    # Relationship to classification (through comment_id)
    classification: Mapped[CommentClassification] = relationship(
        "CommentClassification",
        foreign_keys=[comment_id],
        primaryjoin="QuestionAnswer.comment_id == CommentClassification.comment_id",
        passive_deletes=True,
        overlaps="question_answer",
    )
