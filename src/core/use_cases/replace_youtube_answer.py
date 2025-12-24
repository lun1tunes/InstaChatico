"""Use case for replacing a YouTube answer with a manual update."""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from core.interfaces.services import IYouTubeService
from core.models.question_answer import AnswerStatus, QuestionAnswer
from core.repositories.answer import AnswerRepository
from core.repositories.comment import CommentRepository
from core.utils.time import now_db_utc

logger = logging.getLogger(__name__)


class ReplaceYouTubeAnswerError(Exception):
    """Domain-level error raised when the replace-answer flow fails."""


class ReplaceYouTubeAnswerUseCase:
    """
    Handles manual replacement of an existing YouTube answer.

    Steps:
        1. Delete the previously sent reply on YouTube (if any).
        2. Send the new reply text to YouTube.
        3. Soft-delete the old answer and persist a new QuestionAnswer record.
    """

    def __init__(
        self,
        session: AsyncSession,
        answer_repository_factory: Callable[..., AnswerRepository],
        comment_repository_factory: Callable[..., CommentRepository],
        youtube_service: IYouTubeService,
    ):
        self.session = session
        self.answer_repo = answer_repository_factory(session=session)
        self.comment_repo = comment_repository_factory(session=session)
        self.youtube_service = youtube_service

    async def execute(
        self,
        answer_id: int,
        *,
        new_answer_text: str,
        quality_score: Optional[int] = None,
    ) -> QuestionAnswer:
        """Replace an existing answer with a new YouTube reply."""
        logger.info("Starting manual YouTube answer replacement | answer_id=%s", answer_id)

        answer = await self.answer_repo.get_for_update(answer_id)
        if not answer:
            logger.warning("Answer not found or already replaced | answer_id=%s", answer_id)
            raise ReplaceYouTubeAnswerError("Answer not found")

        comment_id = answer.comment_id
        if not comment_id:
            logger.error("Answer missing comment_id | answer_id=%s", answer_id)
            raise ReplaceYouTubeAnswerError("Answer is not linked to a comment")

        comment = await self.comment_repo.get_by_id(comment_id)
        if not comment:
            raise ReplaceYouTubeAnswerError("Comment not found")

        platform = (getattr(comment, "platform", None) or "").lower()
        if platform != "youtube":
            raise ReplaceYouTubeAnswerError("Comment is not YouTube")

        # Step 1: Attempt to update existing reply (cheaper than delete+insert)
        if answer.reply_id:
            try:
                update_result = await self.youtube_service.update_comment(
                    comment_id=answer.reply_id,
                    text=new_answer_text,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "YouTube reply update failed; falling back to delete+insert | answer_id=%s | reply_id=%s | error=%s",
                    answer_id,
                    answer.reply_id,
                    exc,
                )
            else:
                reply_id = update_result.get("id") or answer.reply_id
                now = now_db_utc()

                try:
                    answer.is_deleted = True
                    answer.reply_sent = True
                    answer.reply_status = "updated"
                    answer.reply_error = None

                    new_answer = QuestionAnswer(
                        comment_id=comment_id,
                        processing_status=AnswerStatus.COMPLETED,
                        answer=new_answer_text,
                        answer_confidence=1.0,  # 100%
                        answer_quality_score=quality_score or 100,
                        last_error=None,
                        retry_count=0,
                        max_retries=answer.max_retries,
                        reply_sent=True,
                        reply_sent_at=now,
                        reply_status="sent",
                        reply_error=None,
                        reply_response=update_result,
                        reply_id=reply_id,
                        is_ai_generated=False,
                    )

                    self.session.add(new_answer)
                    await self.session.flush()
                    await self.session.commit()
                    await self.session.refresh(new_answer)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Failed to persist updated YouTube answer | answer_id=%s", answer_id)
                    await self.session.rollback()
                    raise

                logger.info(
                    "Manual YouTube answer updated | answer_id=%s | new_answer_id=%s | comment_id=%s",
                    answer_id,
                    new_answer.id,
                    comment_id,
                )
                return new_answer

        # Step 2: Delete previous reply on YouTube (if any)
        if answer.reply_id:
            try:
                await self.youtube_service.delete_comment(answer.reply_id)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Failed to delete YouTube reply | answer_id=%s | reply_id=%s | error=%s",
                    answer_id,
                    answer.reply_id,
                    exc,
                )
                await self.session.rollback()
                raise ReplaceYouTubeAnswerError("Failed to delete existing YouTube reply") from exc
            logger.info(
                "Previous YouTube reply deleted | answer_id=%s | reply_id=%s",
                answer_id,
                answer.reply_id,
            )

        # Step 3: Send the new reply
        target_parent_id = comment.parent_id or comment.id
        try:
            send_result = await self.youtube_service.reply_to_comment(
                parent_id=target_parent_id,
                text=new_answer_text,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Failed to send new YouTube reply | answer_id=%s | comment_id=%s | error=%s",
                answer_id,
                comment_id,
                exc,
            )
            await self.session.rollback()
            raise ReplaceYouTubeAnswerError("Failed to send new YouTube reply") from exc

        reply_id = send_result.get("id")
        if not reply_id:
            await self.session.rollback()
            raise ReplaceYouTubeAnswerError("YouTube reply did not return id")

        now = now_db_utc()
        logger.debug(
            "New YouTube reply sent | answer_id=%s | comment_id=%s | reply_id=%s",
            answer_id,
            comment_id,
            reply_id,
        )

        # Step 3: Soft-delete old answer and create the new one
        try:
            answer.is_deleted = True
            answer.reply_sent = False
            answer.reply_status = "deleted"
            answer.reply_error = None

            new_answer = QuestionAnswer(
                comment_id=comment_id,
                processing_status=AnswerStatus.COMPLETED,
                answer=new_answer_text,
                answer_confidence=1.0,  # 100%
                answer_quality_score=quality_score or 100,
                last_error=None,
                retry_count=0,
                max_retries=answer.max_retries,
                reply_sent=True,
                reply_sent_at=now,
                reply_status="sent",
                reply_error=None,
                reply_response=send_result,
                reply_id=reply_id,
                is_ai_generated=False,
            )

            self.session.add(new_answer)
            await self.session.flush()
            await self.session.commit()
            await self.session.refresh(new_answer)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to persist manual YouTube answer replacement | answer_id=%s", answer_id)
            await self.session.rollback()
            raise

        logger.info(
            "Manual YouTube answer replacement completed | answer_id=%s | new_answer_id=%s | comment_id=%s",
            answer_id,
            new_answer.id,
            comment_id,
        )
        return new_answer
