"""Repository pattern implementations for clean data access."""

from .base import BaseRepository
from .comment import CommentRepository
from .classification import ClassificationRepository
from .answer import AnswerRepository
from .media import MediaRepository
from .document import DocumentRepository
from .product_embedding import ProductEmbeddingRepository

__all__ = [
    "BaseRepository",
    "CommentRepository",
    "ClassificationRepository",
    "AnswerRepository",
    "MediaRepository",
    "DocumentRepository",
    "ProductEmbeddingRepository",
]
