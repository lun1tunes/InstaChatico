"""JSON API endpoints for media, comments, and answers."""

from __future__ import annotations

from typing import Any, List, Optional

from fastapi import APIRouter, Body, Depends, Header, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.models import db_helper
from core.repositories.answer import AnswerRepository
from core.repositories.comment import CommentRepository
from core.repositories.media import MediaRepository
from core.repositories.classification import ClassificationRepository
from core.models.comment_classification import CommentClassification, ProcessingStatus
from core.use_cases.hide_comment import HideCommentUseCase
from core.dependencies import get_container
from sqlalchemy import update
from api_v1.comments.serializers import (
    AnswerListResponse,
    AnswerResponse,
    CommentListResponse,
    CommentResponse,
    EmptyResponse,
    ErrorDetail,
    ErrorResponse,
    MediaListResponse,
    MediaResponse,
    PaginationMeta,
    SimpleMeta,
    normalize_classification_label,
    parse_status_filters,
    serialize_answer,
    serialize_comment,
    serialize_media,
    list_classification_types,
)
from core.utils.time import now_db_utc
from core.use_cases.proxy_media_image import MediaImageProxyError
from .schemas import (
    AnswerUpdateRequest,
    ClassificationUpdateRequest,
    CommentVisibilityRequest,
    MediaUpdateRequest,
    ClassificationTypeDTO,
    ClassificationTypesResponse,
)

router = APIRouter(tags=["JSON API"])

MEDIA_DEFAULT_PER_PAGE = 10
MEDIA_MAX_PER_PAGE = 30
COMMENTS_DEFAULT_PER_PAGE = 30
COMMENTS_MAX_PER_PAGE = 100


JSON_API_PATH_PREFIXES = (
    f"{settings.api_v1_prefix}/media",
    f"{settings.api_v1_prefix}/comments",
    f"{settings.api_v1_prefix}/answers",
    f"{settings.api_v1_prefix}/meta",
)


class JsonApiError(Exception):
    def __init__(self, status_code: int, code: int, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message


def require_service_token(authorization: Optional[str] = Header(default=None)) -> None:
    token = settings.json_api.token
    if not token:
        raise JsonApiError(503, 5001, "JSON API token is not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise JsonApiError(401, 4001, "Missing or invalid Authorization header")
    provided = authorization.split(" ", 1)[1].strip()
    if provided != token:
        raise JsonApiError(401, 4002, "Unauthorized")


def _is_json_api_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in JSON_API_PATH_PREFIXES)


async def json_api_error_handler(_: Request, exc: JsonApiError):
    error = ErrorDetail(code=exc.code, message=exc.message)
    body = ErrorResponse(meta=SimpleMeta(error=error))
    return JSONResponse(status_code=exc.status_code, content=body.model_dump())


async def validation_error_handler(request: Request, exc: RequestValidationError):
    if not _is_json_api_path(request.url.path):
        return await request_validation_exception_handler(request, exc)
    error = ErrorDetail(code=4000, message="Validation error", details=exc.errors())
    body = ErrorResponse(meta=SimpleMeta(error=error))
    return JSONResponse(status_code=422, content=body.model_dump())


async def _get_media_or_404(session: AsyncSession, media_id: str) -> Any:
    repo = MediaRepository(session)
    media = await repo.get_by_id(media_id)
    if not media:
        raise JsonApiError(404, 4040, "Media not found")
    return media


async def _get_comment_or_404(session: AsyncSession, comment_id: str) -> Any:
    repo = CommentRepository(session)
    comment = await repo.get_full(comment_id)
    if not comment:
        raise JsonApiError(404, 4041, "Comment not found")
    return comment


async def _get_answer_or_404(session: AsyncSession, answer_id: int) -> Any:
    repo = AnswerRepository(session)
    answer = await repo.get_by_id(answer_id)
    if not answer:
        raise JsonApiError(404, 4042, "Answer not found")
    return answer


async def _get_answer_for_update_or_404(session: AsyncSession, answer_id: int) -> Any:
    repo = AnswerRepository(session)
    answer = await repo.get_for_update(answer_id)
    if not answer:
        raise JsonApiError(404, 4042, "Answer not found")
    return answer


def _clamp_per_page(value: int, default: int, max_value: int) -> int:
    if value is None:
        return default
    return min(max(value, 1), max_value)


@router.get("/media")
async def list_media(
    _: None = Depends(require_service_token),
    page: int = Query(1, ge=1),
    per_page: int = Query(MEDIA_DEFAULT_PER_PAGE, ge=1),
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
):
    per_page = _clamp_per_page(per_page, MEDIA_DEFAULT_PER_PAGE, MEDIA_MAX_PER_PAGE)
    offset = (page - 1) * per_page
    repo = MediaRepository(session)
    total = await repo.count_all()
    items = await repo.list_paginated(offset=offset, limit=per_page)
    payload = [serialize_media(media) for media in items]
    response = MediaListResponse(
        meta=PaginationMeta(page=page, per_page=per_page, total=total),
        payload=payload,
    )
    return response


@router.get("/media/{id}")
async def get_media(
    _: None = Depends(require_service_token),
    media_id: str = Path(..., alias="id"),
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
):
    media = await _get_media_or_404(session, media_id)
    return MediaResponse(meta=SimpleMeta(), payload=serialize_media(media))


@router.patch("/media/{id}")
async def patch_media(
    _: None = Depends(require_service_token),
    media_id: str = Path(..., alias="id"),
    body: MediaUpdateRequest = Body(...),
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
):
    media = await _get_media_or_404(session, media_id)
    container = get_container()
    updated_comment_status = False

    if body.is_comment_enabled is not None and body.is_comment_enabled != media.is_comment_enabled:
        media_service = container.media_service()
        result = await media_service.set_comment_status(media_id, bool(body.is_comment_enabled), session)
        if not result.get("success"):
            raise JsonApiError(502, 5002, "Failed to update Instagram comment status")
        updated_comment_status = True

    if body.context is not None:
        media.media_context = str(body.context)

    if body.is_processing_enabled is not None:
        media.is_processing_enabled = bool(body.is_processing_enabled)

    await session.commit()
    if updated_comment_status:
        await session.refresh(media)

    return MediaResponse(meta=SimpleMeta(), payload=serialize_media(media))
@router.get("/media/{id}/image")
async def proxy_media_image(
    _: None = Depends(require_service_token),
    media_id: str = Path(..., alias="id"),
    child_index: Optional[int] = Query(default=None, ge=0),
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
):
    container = get_container()
    use_case = container.proxy_media_image_use_case(session=session)

    try:
        result = await use_case.execute(media_id=media_id, child_index=child_index)
    except MediaImageProxyError as exc:
        raise JsonApiError(exc.status_code, exc.code, exc.message)

    return StreamingResponse(result.content_stream, media_type=result.content_type, headers=result.headers)


@router.get("/media/{id}/comments")
async def list_media_comments(
    _: None = Depends(require_service_token),
    media_id: str = Path(..., alias="id"),
    page: int = Query(1, ge=1),
    per_page: int = Query(COMMENTS_DEFAULT_PER_PAGE, ge=1),
    status_multi: Optional[List[int]] = Query(default=None, alias="status[]"),
    status_csv: Optional[str] = Query(default=None, alias="status"),
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
):
    await _get_media_or_404(session, media_id)
    per_page = _clamp_per_page(per_page, COMMENTS_DEFAULT_PER_PAGE, COMMENTS_MAX_PER_PAGE)
    offset = (page - 1) * per_page
    status_values: List[int] = []
    if status_multi:
        status_values.extend(status_multi)
    if status_csv:
        for part in status_csv.split(","):
            part = part.strip()
            if part:
                try:
                    status_values.append(int(part))
                except ValueError:
                    raise JsonApiError(400, 4006, "Invalid status filter")

    statuses = parse_status_filters(status_values) if status_values else None
    if status_values and statuses is None:
        raise JsonApiError(400, 4006, "Invalid status filter")

    repo = CommentRepository(session)
    total = await repo.count_for_media(media_id, statuses=statuses)
    items = await repo.list_for_media(media_id, offset=offset, limit=per_page, statuses=statuses)
    payload = [serialize_comment(comment) for comment in items]
    response = CommentListResponse(
        meta=PaginationMeta(page=page, per_page=per_page, total=total),
        payload=payload,
    )
    return response


@router.delete("/comments/{id}")
async def delete_comment(
    _: None = Depends(require_service_token),
    comment_id: str = Path(..., alias="id"),
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
):
    comment = await _get_comment_or_404(session, comment_id)
    await session.delete(comment)
    await session.commit()
    return EmptyResponse(meta=SimpleMeta())


@router.patch("/comments/{id}")
async def patch_comment_visibility(
    _: None = Depends(require_service_token),
    comment_id: str = Path(..., alias="id"),
    body: CommentVisibilityRequest = Body(...),
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
):
    hide = bool(body.is_hidden)
    container = get_container()
    use_case: HideCommentUseCase = container.hide_comment_use_case(session=session)
    result = await use_case.execute(comment_id, hide=hide)
    if result.get("status") == "error":
        raise JsonApiError(502, 5003, "Failed to update comment visibility")

    comment = await _get_comment_or_404(session, comment_id)
    return CommentResponse(meta=SimpleMeta(), payload=serialize_comment(comment))


@router.patch("/comments/{id}/classification")
async def patch_comment_classification(
    _: None = Depends(require_service_token),
    comment_id: str = Path(..., alias="id"),
    body: ClassificationUpdateRequest = Body(...),
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
):
    normalized_label = normalize_classification_label(str(body.type))
    if not normalized_label:
        raise JsonApiError(400, 4009, "Unknown classification type")
    reasoning = str(body.reasoning).strip()

    repo = ClassificationRepository(session)
    classification: Optional[CommentClassification] = await repo.get_by_comment_id(comment_id)
    if not classification:
        classification = CommentClassification(comment_id=comment_id)
        session.add(classification)

    completed_at = now_db_utc()
    if classification.id is None:
        classification.type = normalized_label
        classification.reasoning = reasoning
        classification.confidence = None
        classification.processing_status = ProcessingStatus.COMPLETED
        classification.processing_completed_at = completed_at
        classification.last_error = None
    else:
        await session.execute(
            update(CommentClassification)
            .where(CommentClassification.id == classification.id)
            .values(
                type=normalized_label,
                reasoning=reasoning,
                confidence=None,
                processing_status=ProcessingStatus.COMPLETED,
                processing_completed_at=completed_at,
                last_error=None,
            )
        )
    await session.commit()

    comment = await _get_comment_or_404(session, comment_id)
    return CommentResponse(meta=SimpleMeta(), payload=serialize_comment(comment))


@router.get("/comments/{id}/answers")
async def list_answers_for_comment(
    _: None = Depends(require_service_token),
    comment_id: str = Path(..., alias="id"),
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
):
    comment = await _get_comment_or_404(session, comment_id)
    answers = []
    if comment.question_answer:
        answers.append(serialize_answer(comment.question_answer))
    return AnswerListResponse(meta=SimpleMeta(), payload=answers)


@router.patch("/answers/{id}")
async def patch_answer(
    _: None = Depends(require_service_token),
    answer_id: int = Path(..., alias="id"),
    body: AnswerUpdateRequest = Body(...),
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
):
    answer = await _get_answer_or_404(session, answer_id)
    answer.answer = str(body.answer)

    if body.quality_score is not None:
        answer.answer_quality_score = int(body.quality_score)

    if body.confidence is not None:
        answer.answer_confidence = body.confidence / 100

    await session.commit()
    await session.refresh(answer)
    return AnswerResponse(meta=SimpleMeta(), payload=serialize_answer(answer))


@router.delete("/answers/{id}")
async def delete_answer(
    _: None = Depends(require_service_token),
    answer_id: int = Path(..., alias="id"),
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
):
    answer = await _get_answer_for_update_or_404(session, answer_id)
    if not answer.reply_id or answer.reply_status == "deleted":
        raise JsonApiError(400, 4012, "Answer does not have an Instagram reply")

    instagram_service = get_container().instagram_service()
    result = await instagram_service.delete_comment_reply(answer.reply_id)
    if not result.get("success"):
        raise JsonApiError(502, 5004, "Failed to delete reply on Instagram")

    answer.reply_sent = False
    answer.reply_status = "deleted"
    answer.reply_error = None
    await session.commit()
    return EmptyResponse(meta=SimpleMeta())
@router.get("/meta/classification-types")
async def get_classification_types(
    _: None = Depends(require_service_token),
):
    items = [
        ClassificationTypeDTO(code=code, label=label)
        for code, label in list_classification_types()
    ]
    return ClassificationTypesResponse(meta=SimpleMeta(), payload=items)
