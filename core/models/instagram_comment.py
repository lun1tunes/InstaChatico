from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base

class InstagramComment(Base):
    __tablename__ = "instagram_comments"
    
    id: Mapped[str] = mapped_column(primary_key=True)
    media_id: Mapped[str]
    user_id: Mapped[str]
    username: Mapped[str]
    text: Mapped[str]
    created_at: Mapped[datetime]
    raw_data = mapped_column(JSONB)