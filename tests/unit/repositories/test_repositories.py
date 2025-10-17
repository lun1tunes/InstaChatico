"""
Unit tests for Repository layer.

Tests data access logic without external dependencies.
"""

import pytest
from datetime import datetime
from sqlalchemy import select

from core.repositories.comment import CommentRepository
from core.repositories.classification import ClassificationRepository
from core.repositories.answer import AnswerRepository
from core.models import InstagramComment, CommentClassification, QuestionAnswer


# ============================================================================
# COMMENT REPOSITORY TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.repository
class TestCommentRepository:
    """Test CommentRepository methods."""

    async def test_create_comment(self, db_session):
        """Test creating a new comment."""
        # Arrange
        repo = CommentRepository(db_session)
        comment_data = {
            "id": "comment_123",
            "media_id": "media_123",
            "user_id": "user_123",
            "username": "test_user",
            "text": "Test comment",
            "created_at": datetime.utcnow(),
            "raw_data": {},
        }

        # Act
        comment = await repo.create(comment_data)

        # Assert
        assert comment.id == "comment_123"
        assert comment.username == "test_user"
        assert comment.text == "Test comment"

    async def test_get_comment_by_id(self, db_session, instagram_comment_factory):
        """Test retrieving a comment by ID."""
        # Arrange
        repo = CommentRepository(db_session)
        created_comment = await instagram_comment_factory(comment_id="test_123")

        # Act
        comment = await repo.get("test_123")

        # Assert
        assert comment is not None
        assert comment.id == "test_123"
        assert comment.username == created_comment.username

    async def test_get_nonexistent_comment_returns_none(self, db_session):
        """Test that getting non-existent comment returns None."""
        # Arrange
        repo = CommentRepository(db_session)

        # Act
        comment = await repo.get("nonexistent_id")

        # Assert
        assert comment is None

    async def test_update_comment(self, db_session, instagram_comment_factory):
        """Test updating a comment."""
        # Arrange
        repo = CommentRepository(db_session)
        comment = await instagram_comment_factory(text="Original text")

        # Act
        updated = await repo.update(comment.id, {"text": "Updated text"})

        # Assert
        assert updated.text == "Updated text"
        assert updated.id == comment.id

    async def test_delete_comment(self, db_session, instagram_comment_factory):
        """Test deleting a comment."""
        # Arrange
        repo = CommentRepository(db_session)
        comment = await instagram_comment_factory()

        # Act
        result = await repo.delete(comment.id)

        # Assert
        assert result is True
        deleted_comment = await repo.get(comment.id)
        assert deleted_comment is None

    async def test_get_by_conversation_id(self, db_session, instagram_comment_factory):
        """Test getting comments by conversation ID."""
        # Arrange
        repo = CommentRepository(db_session)
        conv_id = "conversation_123"
        await instagram_comment_factory(conversation_id=conv_id, text="Comment 1")
        await instagram_comment_factory(conversation_id=conv_id, text="Comment 2")
        await instagram_comment_factory(conversation_id="other_conv", text="Comment 3")

        # Act
        comments = await repo.get_by_conversation_id(conv_id)

        # Assert
        assert len(comments) == 2
        assert all(c.conversation_id == conv_id for c in comments)

    async def test_comment_persistence(self, db_session):
        """Test that created comment persists in database."""
        # Arrange
        repo = CommentRepository(db_session)
        comment_data = {
            "id": "persist_test",
            "media_id": "media_123",
            "user_id": "user_123",
            "username": "test",
            "text": "Persist test",
            "created_at": datetime.utcnow(),
            "raw_data": {},
        }

        # Act
        await repo.create(comment_data)
        await db_session.commit()

        # Verify persistence with fresh query
        result = await db_session.execute(
            select(InstagramComment).where(InstagramComment.id == "persist_test")
        )
        persisted_comment = result.scalar_one_or_none()

        # Assert
        assert persisted_comment is not None
        assert persisted_comment.text == "Persist test"


# ============================================================================
# CLASSIFICATION REPOSITORY TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.repository
class TestClassificationRepository:
    """Test ClassificationRepository methods."""

    async def test_create_classification(self, db_session, instagram_comment_factory):
        """Test creating a classification."""
        # Arrange
        comment = await instagram_comment_factory()
        repo = ClassificationRepository(db_session)
        clf_data = {
            "comment_id": comment.id,
            "classification": "question / inquiry",
            "confidence": 0.95,
            "reasoning": "Contains question mark",
            "input_tokens": 100,
            "output_tokens": 50,
        }

        # Act
        classification = await repo.create(clf_data)

        # Assert
        assert classification.comment_id == comment.id
        assert classification.classification == "question / inquiry"
        assert classification.confidence == 0.95

    async def test_get_by_comment_id(self, db_session, instagram_comment_factory, classification_factory):
        """Test getting classification by comment ID."""
        # Arrange
        comment = await instagram_comment_factory()
        await classification_factory(comment_id=comment.id, classification="positive")
        repo = ClassificationRepository(db_session)

        # Act
        classification = await repo.get_by_comment_id(comment.id)

        # Assert
        assert classification is not None
        assert classification.comment_id == comment.id
        assert classification.classification == "positive"

    async def test_get_pending_retries(self, db_session, instagram_comment_factory, classification_factory):
        """Test getting classifications that need retry."""
        # Arrange
        comment1 = await instagram_comment_factory()
        comment2 = await instagram_comment_factory()
        comment3 = await instagram_comment_factory()

        await classification_factory(comment_id=comment1.id, classification="retry", retry_count=1)
        await classification_factory(comment_id=comment2.id, classification="retry", retry_count=2)
        await classification_factory(comment_id=comment3.id, classification="positive", retry_count=0)

        repo = ClassificationRepository(db_session)

        # Act
        pending = await repo.get_pending_retries(max_retries=3)

        # Assert
        assert len(pending) == 2
        assert all(c.classification == "retry" for c in pending)


# ============================================================================
# ANSWER REPOSITORY TESTS
# ============================================================================


@pytest.mark.unit
@pytest.mark.repository
class TestAnswerRepository:
    """Test AnswerRepository methods."""

    async def test_create_answer(self, db_session, instagram_comment_factory):
        """Test creating an answer."""
        # Arrange
        comment = await instagram_comment_factory()
        repo = AnswerRepository(db_session)
        answer_data = {
            "comment_id": comment.id,
            "question_text": "Test question?",
            "answer_text": "Test answer",
            "confidence": 0.9,
            "quality_score": 0.85,
            "processing_time_ms": 1500,
        }

        # Act
        answer = await repo.create(answer_data)

        # Assert
        assert answer.comment_id == comment.id
        assert answer.answer_text == "Test answer"
        assert answer.confidence == 0.9

    async def test_get_by_comment_id(self, db_session, instagram_comment_factory, answer_factory):
        """Test getting answer by comment ID."""
        # Arrange
        comment = await instagram_comment_factory()
        await answer_factory(comment_id=comment.id, answer_text="Saved answer")
        repo = AnswerRepository(db_session)

        # Act
        answer = await repo.get_by_comment_id(comment.id)

        # Assert
        assert answer is not None
        assert answer.comment_id == comment.id
        assert answer.answer_text == "Saved answer"

    async def test_answer_with_tokens(self, db_session, instagram_comment_factory):
        """Test creating answer with token usage."""
        # Arrange
        comment = await instagram_comment_factory()
        repo = AnswerRepository(db_session)
        answer_data = {
            "comment_id": comment.id,
            "question_text": "Question",
            "answer_text": "Answer",
            "input_tokens": 200,
            "output_tokens": 150,
        }

        # Act
        answer = await repo.create(answer_data)

        # Assert
        assert answer.input_tokens == 200
        assert answer.output_tokens == 150
