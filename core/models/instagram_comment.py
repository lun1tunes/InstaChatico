from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base

class InstagramComment(Base):
    media_id: Mapped[int]
    user_id: Mapped[str]
    username: Mapped[str]
    text: Mapped[str]
    created_at: Mapped[datetime]
    raw_data = mapped_column(JSONB)