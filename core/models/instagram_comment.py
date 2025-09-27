from __future__ import annotations
from typing import TYPE_CHECKING
from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from .base import Base

if TYPE_CHECKING:
    from .comment_classification import CommentClassification
    from .question_answer import QuestionAnswer
    
class InstagramComment(Base):
    __tablename__ = "instagram_comments"
    
    id: Mapped[str] = mapped_column(primary_key=True)
    media_id: Mapped[str]
    user_id: Mapped[str]
    username: Mapped[str]
    text: Mapped[str]
    created_at: Mapped[datetime]
    raw_data = mapped_column(JSONB)
    
    # Relationship to classification
    classification: Mapped[CommentClassification] = relationship(
        "CommentClassification", 
        back_populates="comment",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    
    # Relationship to question answer
    question_answer: Mapped[QuestionAnswer] = relationship(
        "QuestionAnswer",
        foreign_keys="QuestionAnswer.comment_id",
        primaryjoin="InstagramComment.id == QuestionAnswer.comment_id",
        uselist=False,
        passive_deletes=True,
        overlaps="classification",
    )