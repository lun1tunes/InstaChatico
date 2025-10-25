import pytest
from datetime import datetime, timezone

from core.models.media import Media
from core.models.instagram_comment import InstagramComment
from core.models.comment_classification import CommentClassification, ProcessingStatus
from core.models.question_answer import QuestionAnswer, AnswerStatus
from api_v1.comments.serializers import (
    format_datetime,
    classification_type_to_code,
    parse_status_filters,
    serialize_media,
    serialize_comment,
    serialize_answer,
)
from api_v1.comments.schemas import MediaDTO, CommentDTO, AnswerDTO


def _build_media():
    return Media(
        id="media_1",
        permalink="https://instagram.com/p/media_1",
        caption="Caption",
        media_url="https://cdn/media.jpg",
        media_type="IMAGE",
        comments_count=5,
        like_count=10,
        shortcode="MEDIA1",
        is_comment_enabled=True,
        is_processing_enabled=True,
    )


def _build_comment(media_id="media_1"):
    return InstagramComment(
        id="comment_1",
        media_id=media_id,
        user_id="user",
        username="tester",
        text="Hello",
        created_at=datetime.now(timezone.utc),
        is_hidden=False,
        raw_data={},
    )


def _build_classification(comment_id="comment_1"):
    classification = CommentClassification(
        comment_id=comment_id,
        processing_status=ProcessingStatus.COMPLETED,
        processing_completed_at=datetime.now(timezone.utc),
        type="question / inquiry",
        confidence=88,
        reasoning="auto",
    )
    classification.id = 123
    return classification


def _build_answer(comment_id="comment_1"):
    answer = QuestionAnswer(
        comment_id=comment_id,
        answer="Thanks!",
        answer_confidence=0.75,
        answer_quality_score=90,
        reply_sent=True,
        reply_status="sent",
        processing_status=AnswerStatus.COMPLETED,
    )
    answer.id = 456
    return answer


def test_serialize_media_returns_dto():
    media = _build_media()
    dto = serialize_media(media)

    assert isinstance(dto, MediaDTO)
    assert dto.id == media.id
    assert dto.type == 1  # IMAGE
    assert dto.is_processing_enabled is True


def test_serialize_comment_with_relations():
    media = _build_media()
    comment = _build_comment(media.id)
    comment.classification = _build_classification(comment.id)
    comment.question_answer = _build_answer(comment.id)

    dto = serialize_comment(comment)

    assert isinstance(dto, CommentDTO)
    assert dto.classification.type == 4  # question / inquiry
    assert dto.answers and isinstance(dto.answers[0], AnswerDTO)


def test_serialize_answer_confidence_conversion():
    answer = _build_answer()
    dto = serialize_answer(answer)

    assert dto.confidence == 75
    assert dto.reply_sent is True


def test_format_datetime_returns_iso():
    dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert format_datetime(dt) == "2024-01-01T00:00:00Z"


def test_classification_type_to_code_handles_synonyms():
    assert classification_type_to_code("positive feedback") == 1
    assert classification_type_to_code("positive feedback / appreciation") is None
    assert classification_type_to_code("unknown") is None


def test_parse_status_filters_valid_and_invalid():
    result = parse_status_filters([3])
    assert result == [ProcessingStatus.COMPLETED]

    assert parse_status_filters([999]) is None
