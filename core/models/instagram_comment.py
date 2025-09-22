from __future__ import annotations
from typing import TYPE_CHECKING
from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from .base import Base

if TYPE_CHECKING:
    from .comment_classification import CommentClassification
    
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