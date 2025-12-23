"""Use case for creating or replacing manual YouTube answers."""

from __future__ import annotations

import logging
from typing import Any, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from core.interfaces.services import IYouTubeService
from core.models.question_answer import AnswerStatus, QuestionAnswer
from core.repositories.answer import AnswerRepository
from core.repositories.comment import CommentRepository
from core.services.base_service import BaseService
from core.utils.time import now_db_utc
from core.interfaces.agents import IAgentSessionService
from .replace_youtube_answer import ReplaceYouTubeAnswerUseCase, ReplaceYouTubeAnswerError

logger = logging.getLogger(__name__)


class ManualYouTubeAnswerCreateError(Exception):
    """Raised when manual YouTube answer creation cannot be completed."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.status_code = status_code


class CreateManualYouTubeAnswerUseCase:
    """Creates a new manual answer for a YouTube comment, replacing existing reply if necessary."""

    def __init__(
        self,
        session: AsyncSession,
        comment_repository_factory: Callable[..., CommentRepository],
        answer_repository_factory: Callable[..., AnswerRepository],
        youtube_service: IYouTubeService,
        replace_answer_use_case_factory: Callable[..., ReplaceYouTubeAnswerUseCase],
        session_service: IAgentSessionService,
    ) -> None:
        self.session = session
        self.comment_repo = comment_repository_factory(session=session)
        self.answer_repo = answer_repository_factory(session=session)
        self.youtube_service = youtube_service
        self._replace_use_case_factory = replace_answer_use_case_factory
        self.session_service = session_service

    async def execute(self, comment_id: str, *, answer_text: str) -> QuestionAnswer:
        logger.info("Manual YouTube answer create request | comment_id=%s", comment_id)

        comment = await self.comment_repo.get_by_id(comment_id)
        if not comment:
            logger.warning("Comment not found for manual YouTube answer | comment_id=%s", comment_id)
            raise ManualYouTubeAnswerCreateError("Comment not found", status_code=404)

        platform = (getattr(comment, "platform", None) or "").lower()
        if platform != "youtube":
            raise ManualYouTubeAnswerCreateError("Comment is not YouTube", status_code=400)

        # Avoid replying to our own channel's comments
        author_channel_id = None
        raw_snippet = (comment.raw_data or {}).get("snippet", {}) if comment.raw_data else {}
        author_channel_obj = raw_snippet.get("authorChannelId") or {}
        if isinstance(author_channel_obj, dict):
            author_channel_id = author_channel_obj.get("value")
        try:
            my_channel_id = await self.youtube_service.get_account_id()
        except Exception:
            my_channel_id = None
        if my_channel_id and author_channel_id and my_channel_id == author_channel_id:
            raise ManualYouTubeAnswerCreateError("Cannot reply to own comment", status_code=400)

        conversation_id = self._resolve_conversation_id(comment)
        if conversation_id and not getattr(comment, "conversation_id", None):
            comment.conversation_id = conversation_id

        existing_answer = await self.answer_repo.get_by_comment_id(comment_id)
        if existing_answer:
            replace_use_case = self._replace_use_case_factory(session=self.session)
            try:
                new_answer = await replace_use_case.execute(
                    answer_id=existing_answer.id,
                    new_answer_text=answer_text,
                )
            except ReplaceYouTubeAnswerError as exc:
                raise ManualYouTubeAnswerCreateError(str(exc), status_code=502) from exc

            await self._inject_into_conversation(conversation_id, comment, answer_text)
            return new_answer

        target_parent_id = comment.parent_id or comment.id
        try:
            result = await self.youtube_service.reply_to_comment(parent_id=target_parent_id, text=answer_text)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Failed to send manual YouTube reply | comment_id=%s | error=%s",
                comment_id,
                exc,
            )
            raise ManualYouTubeAnswerCreateError("Failed to send YouTube reply", status_code=502) from exc

        reply_id = result.get("id")
        if not reply_id:
            raise ManualYouTubeAnswerCreateError("YouTube reply did not return id", status_code=502)

        now = now_db_utc()
        new_answer = QuestionAnswer(
            comment_id=comment_id,
            processing_status=AnswerStatus.COMPLETED,
            answer=answer_text,
            answer_confidence=1.0,
            answer_quality_score=100,
            retry_count=0,
            max_retries=5,
            reply_sent=True,
            reply_sent_at=now,
            reply_status="sent",
            reply_error=None,
            reply_response=result,
            reply_id=reply_id,
            is_ai_generated=False,
        )

        try:
            self.session.add(new_answer)
            if not getattr(comment, "conversation_id", None):
                comment.conversation_id = conversation_id
            await self.session.flush()
            await self.session.commit()
            await self.session.refresh(new_answer)
        except Exception:
            logger.exception(
                "Failed to persist manual YouTube answer creation | comment_id=%s",
                comment_id,
            )
            await self.session.rollback()
            raise

        logger.info("Manual YouTube answer created | comment_id=%s | answer_id=%s", comment_id, new_answer.id)
        await self._inject_into_conversation(conversation_id, comment, answer_text)
        return new_answer

    def _resolve_conversation_id(self, comment) -> str:
        if getattr(comment, "conversation_id", None):
            return comment.conversation_id
        root_id = comment.parent_id or comment.id
        return f"first_question_comment_{root_id}"

    async def _inject_into_conversation(self, conversation_id: str, comment, answer_text: str) -> None:
        if not conversation_id or not answer_text:
            return

        try:
            session = self.session_service.get_session(conversation_id)
            username = getattr(comment, "username", None)
            user_text = getattr(comment, "text", "") or ""
            if username:
                user_message = f"@{username}: {user_text}"
            else:
                user_message = user_text
            user_message = BaseService._sanitize_input(user_message) if user_message else None

            items = []
            if user_message:
                items.append({"role": "user", "content": user_message})
            items.append({"role": "assistant", "content": answer_text})
            await session.add_items(items)
            logger.debug(
                "Manual YouTube answer appended to conversation | conversation_id=%s | user_included=%s",
                conversation_id,
                bool(user_message),
            )
        except Exception as exc:
            logger.warning(
                "Failed to append manual YouTube answer to conversation | conversation_id=%s | error=%s",
                conversation_id,
                exc,
            )
