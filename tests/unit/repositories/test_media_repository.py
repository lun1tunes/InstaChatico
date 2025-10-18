"""
Unit tests for MediaRepository.

Tests data access logic for Instagram media without external dependencies.
"""

import pytest
from datetime import datetime

from core.repositories.media import MediaRepository
from core.models.media import Media


@pytest.mark.unit
@pytest.mark.repository
class TestMediaRepository:
    """Test MediaRepository methods."""

    async def test_create_media(self, db_session):
        """Test creating a new media record."""
        # Arrange
        repo = MediaRepository(db_session)
        media_entity = Media(
            id="media_123",
            media_type="IMAGE",
            media_url="https://example.com/image.jpg",
            caption="Test caption",
            permalink="https://instagram.com/p/test",
        )

        # Act
        media = await repo.create(media_entity)

        # Assert
        assert media.id == "media_123"
        assert media.media_type == "IMAGE"
        assert media.media_url == "https://example.com/image.jpg"
        assert media.caption == "Test caption"

    async def test_get_media_by_id(self, db_session, media_factory):
        """Test retrieving media by ID."""
        # Arrange
        repo = MediaRepository(db_session)
        created_media = await media_factory(media_id="media_456")

        # Act
        media = await repo.get_by_id("media_456")

        # Assert
        assert media is not None
        assert media.id == "media_456"

    async def test_get_nonexistent_media_returns_none(self, db_session):
        """Test that getting non-existent media returns None."""
        # Arrange
        repo = MediaRepository(db_session)

        # Act
        media = await repo.get_by_id("nonexistent_media")

        # Assert
        assert media is None

    async def test_get_with_comments(self, db_session, media_factory, instagram_comment_factory):
        """Test getting media with comments eagerly loaded."""
        # Arrange
        repo = MediaRepository(db_session)
        media = await media_factory(media_id="media_with_comments")
        await instagram_comment_factory(media_id=media.id, text="Comment 1")
        await instagram_comment_factory(media_id=media.id, text="Comment 2")

        # Act
        result = await repo.get_with_comments(media.id)

        # Assert
        assert result is not None
        assert result.id == media.id
        assert len(result.comments) == 2

    async def test_get_media_needing_analysis(self, db_session, media_factory):
        """Test getting media that needs AI analysis."""
        # Arrange
        repo = MediaRepository(db_session)

        # Create media needing analysis
        await media_factory(
            media_type="IMAGE",
            media_url="https://example.com/needs_analysis.jpg",
            media_context=None
        )

        # Create carousel needing analysis
        await media_factory(
            media_type="CAROUSEL_ALBUM",
            media_url="https://example.com/carousel.jpg",
            media_context=None
        )

        # Create media already analyzed
        await media_factory(
            media_type="IMAGE",
            media_url="https://example.com/already_analyzed.jpg",
            media_context="This is analyzed content"
        )

        # Create video (shouldn't need analysis)
        await media_factory(
            media_type="VIDEO",
            media_url="https://example.com/video.mp4",
            media_context=None
        )

        # Act
        media_list = await repo.get_media_needing_analysis(limit=10)

        # Assert
        assert len(media_list) == 2
        assert all(m.media_type in ["IMAGE", "CAROUSEL_ALBUM"] for m in media_list)
        assert all(m.media_context is None for m in media_list)

    async def test_get_media_needing_analysis_with_limit(self, db_session, media_factory):
        """Test that get_media_needing_analysis respects limit."""
        # Arrange
        repo = MediaRepository(db_session)
        for i in range(5):
            await media_factory(
                media_type="IMAGE",
                media_url=f"https://example.com/image_{i}.jpg",
                media_context=None
            )

        # Act
        media_list = await repo.get_media_needing_analysis(limit=3)

        # Assert
        assert len(media_list) == 3

    async def test_exists_by_id_true(self, db_session, media_factory):
        """Test exists_by_id returns True for existing media."""
        # Arrange
        repo = MediaRepository(db_session)
        media = await media_factory(media_id="existing_media")

        # Act
        exists = await repo.exists_by_id(media.id)

        # Assert
        assert exists is True

    async def test_exists_by_id_false(self, db_session):
        """Test exists_by_id returns False for non-existent media."""
        # Arrange
        repo = MediaRepository(db_session)

        # Act
        exists = await repo.exists_by_id("nonexistent_media")

        # Assert
        assert exists is False

    async def test_update_media(self, db_session, media_factory):
        """Test updating media."""
        # Arrange
        repo = MediaRepository(db_session)
        media = await media_factory(caption="Original caption")

        # Act
        media.caption = "Updated caption"
        updated = await repo.update(media)

        # Assert
        assert updated.caption == "Updated caption"

    async def test_delete_media(self, db_session, media_factory):
        """Test deleting media."""
        # Arrange
        repo = MediaRepository(db_session)
        media = await media_factory()

        # Act
        await repo.delete(media)

        # Assert
        deleted = await repo.get_by_id(media.id)
        assert deleted is None

    async def test_list_all_media(self, db_session, media_factory):
        """Test listing all media."""
        # Arrange
        repo = MediaRepository(db_session)
        await media_factory()
        await media_factory()
        await media_factory()

        # Act
        media_list = await repo.get_all()

        # Assert
        assert len(media_list) >= 3

    async def test_create_carousel_media(self, db_session):
        """Test creating carousel media with children URLs."""
        # Arrange
        repo = MediaRepository(db_session)
        media_entity = Media(
            id="carousel_123",
            media_type="CAROUSEL_ALBUM",
            media_url="https://example.com/carousel.jpg",
            permalink="https://instagram.com/p/carousel",
            children_media_urls=["url1.jpg", "url2.jpg", "url3.jpg"],
        )

        # Act
        media = await repo.create(media_entity)

        # Assert
        assert media.media_type == "CAROUSEL_ALBUM"
        assert media.children_media_urls == ["url1.jpg", "url2.jpg", "url3.jpg"]

    async def test_update_media_context(self, db_session, media_factory):
        """Test updating media context after AI analysis."""
        # Arrange
        repo = MediaRepository(db_session)
        media = await media_factory(media_context=None)

        # Act
        media.media_context = "AI-generated description of the image"
        updated = await repo.update(media)

        # Assert
        assert updated.media_context == "AI-generated description of the image"

    async def test_media_with_multiple_comments(self, db_session, media_factory, instagram_comment_factory):
        """Test media with multiple comments relationship."""
        # Arrange
        repo = MediaRepository(db_session)
        media = await media_factory()

        for i in range(5):
            await instagram_comment_factory(media_id=media.id, text=f"Comment {i}")

        # Act
        result = await repo.get_with_comments(media.id)

        # Assert
        assert len(result.comments) == 5

    async def test_get_media_needing_analysis_excludes_no_url(self, db_session, media_factory):
        """Test that media without URL is excluded from analysis queue."""
        # Arrange
        repo = MediaRepository(db_session)
        await media_factory(media_type="IMAGE", media_url=None, media_context=None)

        # Act
        media_list = await repo.get_media_needing_analysis(limit=10)

        # Assert
        assert len(media_list) == 0

    async def test_get_with_comments_no_comments(self, db_session, media_factory):
        """Test getting media with comments when there are none."""
        # Arrange
        repo = MediaRepository(db_session)
        media = await media_factory()

        # Act
        result = await repo.get_with_comments(media.id)

        # Assert
        assert result is not None
        assert len(result.comments) == 0
