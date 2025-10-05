"""Repository pattern implementations for clean data access."""

from .base import BaseRepository
from .comment import CommentRepository
from .classification import ClassificationRepository

__all__ = [
    "BaseRepository",
    "CommentRepository",
    "ClassificationRepository",
]
