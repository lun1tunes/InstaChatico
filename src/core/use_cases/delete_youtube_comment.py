"""Delete YouTube comment use case."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from core.interfaces.services import IYouTubeService
from core.exceptions.youtube import MissingYouTubeAuth, QuotaExceeded
from core.repositories.comment import CommentRepository
from core.utils.decorators import handle_task_errors

logger = logging.getLogger(__name__)


class DeleteYouTubeCommentUseCase:
    """
    Use case for deleting YouTube comments.
    """

    def __init__(
        self,
        session: AsyncSession,
        youtube_service: IYouTubeService,
        comment_repository_factory: Callable[..., CommentRepository],
    ):
        self.session = session
        self.youtube_service = youtube_service
        self.comment_repo: CommentRepository = comment_repository_factory(session=session)

    @handle_task_errors()
    async def execute(self, comment_id: str, initiator: str = "ai") -> Dict[str, Any]:
        logger.info("Starting delete comment flow (YouTube) | comment_id=%s", comment_id)

        comment_id = comment_id.strip()
        comment = await self.comment_repo.get_by_id(comment_id)
        if not comment:
            logger.error("Comment not found | comment_id=%s | operation=delete_youtube_comment", comment_id)
            return {"status": "error", "reason": f"Comment {comment_id} not found"}

        if comment.is_deleted:
            logger.info("Comment already marked deleted | comment_id=%s", comment_id)
            return {"status": "skipped", "reason": "Comment already deleted"}

        author_channel_id = _extract_author_channel_id(comment)
        my_channel_id = await _resolve_my_channel_id(self.youtube_service)
        should_moderate = bool(author_channel_id and my_channel_id and author_channel_id != my_channel_id)

        try:
            if should_moderate and hasattr(self.youtube_service, "set_comment_moderation_status"):
                await self.youtube_service.set_comment_moderation_status(comment_id, status="rejected")
            else:
                await self.youtube_service.delete_comment(comment_id)
        except MissingYouTubeAuth:
            return {"status": "error", "reason": "forbidden"}
        except QuotaExceeded:
            return {"status": "error", "reason": "quota_exceeded"}
        except Exception as exc:  # noqa: BLE001
            status_code, reasons, message = _extract_youtube_error(exc)
            logger.error(
                "Failed to delete comment via YouTube API | comment_id=%s | status=%s | reasons=%s | error=%s",
                comment_id,
                status_code,
                reasons,
                message or exc,
            )
            not_found = (
                status_code == 404
                or "commentNotFound" in reasons
                or _contains_phrase(message, "not found")
                or _contains_phrase(message, "not be found")
            )
            if not_found:
                affected = await self.comment_repo.mark_deleted_with_descendants(
                    comment_id,
                    deleted_by_ai=(initiator == "ai"),
                )
                await self.session.commit()
                logger.info("Comment already missing on YouTube; marked deleted in DB | comment_id=%s", comment_id)
                return {"status": "skipped", "reason": "comment_not_found", "deleted_count": affected}

            forbidden_reasons = {"forbidden", "insufficientPermissions", "ineligibleAccount", "notAuthorized"}
            if status_code in {401, 403} or reasons.intersection(forbidden_reasons):
                return {"status": "error", "reason": "forbidden"}

            if (
                "processingFailure" in reasons
                and not should_moderate
                and hasattr(self.youtube_service, "set_comment_moderation_status")
            ):
                try:
                    await self.youtube_service.set_comment_moderation_status(comment_id, status="rejected")
                    affected = await self.comment_repo.mark_deleted_with_descendants(
                        comment_id,
                        deleted_by_ai=(initiator == "ai"),
                    )
                    await self.session.commit()
                    logger.info(
                        "Comment rejected via moderation fallback | comment_id=%s | affected_rows=%s",
                        comment_id,
                        affected,
                    )
                    return {"status": "success", "deleted_count": affected, "action": "moderated"}
                except Exception as moderation_exc:  # noqa: BLE001
                    logger.warning(
                        "Moderation fallback failed | comment_id=%s | error=%s",
                        comment_id,
                        moderation_exc,
                    )

            return {"status": "error", "reason": message or str(exc)}

        affected = await self.comment_repo.mark_deleted_with_descendants(
            comment_id, deleted_by_ai=(initiator == "ai")
        )
        await self.session.commit()

        logger.info("Comment deleted in DB | comment_id=%s | affected_rows=%s", comment_id, affected)
        return {
            "status": "success",
            "deleted_count": affected,
        }


def _contains_phrase(value: str | None, phrase: str) -> bool:
    if not value:
        return False
    return phrase.lower() in value.lower()


def _extract_author_channel_id(comment) -> str | None:
    raw = getattr(comment, "raw_data", None)
    if not isinstance(raw, dict):
        return None
    snippet = raw.get("snippet") if isinstance(raw.get("snippet"), dict) else {}
    author = snippet.get("authorChannelId") if isinstance(snippet, dict) else {}
    if isinstance(author, dict):
        value = author.get("value")
        return str(value) if value else None
    return None


async def _resolve_my_channel_id(youtube_service: IYouTubeService) -> str | None:
    if hasattr(youtube_service, "get_account_id"):
        try:
            return await youtube_service.get_account_id()  # type: ignore[attr-defined]
        except Exception:
            return None
    return None


def _extract_youtube_error(exc: Exception) -> tuple[int | None, set[str], str | None]:
    """Best-effort extraction of YouTube error metadata without hard dependency."""
    status_code = _extract_status_code(exc)

    reasons: set[str] = set()
    message: str | None = None

    details = getattr(exc, "error_details", None)
    if isinstance(details, list):
        for item in details:
            if isinstance(item, dict):
                reason = item.get("reason")
                if reason:
                    reasons.add(str(reason))
                if item.get("message") and not message:
                    message = str(item["message"])

    content = getattr(exc, "content", None)
    if content:
        try:
            raw = content.decode("utf-8") if isinstance(content, (bytes, bytearray)) else str(content)
            payload = json.loads(raw)
            error_obj = payload.get("error", {}) if isinstance(payload, dict) else {}
            for err in error_obj.get("errors", []) if isinstance(error_obj, dict) else []:
                if isinstance(err, dict):
                    reason = err.get("reason")
                    if reason:
                        reasons.add(str(reason))
                    if err.get("message") and not message:
                        message = str(err["message"])
        except Exception:
            pass

    if not message:
        if hasattr(exc, "_get_reason"):
            try:
                message = str(exc._get_reason())  # type: ignore[attr-defined]
            except Exception:
                message = None
    if not message:
        message = str(exc) if exc else None

    return status_code, reasons, message


def _extract_status_code(exc: Exception) -> int | None:
    status_code = _coerce_status_code(getattr(exc, "status_code", None))
    if status_code is not None:
        return status_code
    status_code = _coerce_status_code(getattr(exc, "status", None))
    if status_code is not None:
        return status_code
    resp = getattr(exc, "resp", None)
    if resp is None:
        return None
    if isinstance(resp, dict):
        return _coerce_status_code(resp.get("status") or resp.get("status_code"))
    status_code = _coerce_status_code(getattr(resp, "status", None))
    if status_code is not None:
        return status_code
    return _coerce_status_code(getattr(resp, "status_code", None))


def _coerce_status_code(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None
