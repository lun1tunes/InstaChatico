import datetime
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.logging_config import trace_id_ctx
from core.models import db_helper
from core.models.comment_classification import CommentClassification, ProcessingStatus
from core.models.instagram_comment import InstagramComment
from core.models.question_answer import QuestionAnswer
from core.tasks.classification_tasks import classify_comment_task

from . import crud
from .schemas import WebhookPayload

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Webhooks"])


@router.get("/")
async def webhook_verification(request: Request):
    # Instagram sends parameters with dots, not underscores
    hub_mode = request.query_params.get("hub.mode")
    hub_challenge = request.query_params.get("hub.challenge")
    hub_verify_token = request.query_params.get("hub.verify_token")

    # Validate required parameters
    if not all([hub_mode, hub_challenge, hub_verify_token]):
        raise HTTPException(status_code=422, detail="Missing required parameters")

    # Check verify token
    if hub_verify_token != settings.app_webhook_verify_token:
        raise HTTPException(status_code=403, detail="Invalid verify token")

    logger.info(f"Verification completed successfully")
    return PlainTextResponse(hub_challenge)


@router.post("")
@router.post("/")
async def process_webhook(
    request: Request,
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
):
    try:
        # If webhook includes its own trace id, bind it early
        incoming_trace = request.headers.get("X-Trace-Id")
        if incoming_trace:
            trace_id_ctx.set(incoming_trace)
        logger.info("Processing webhook request")
        body_bytes = getattr(request.state, "body", None) or await request.body()
        payload = json.loads(body_bytes.decode())
        logger.debug(f"Parsed payload: {payload}")
        webhook_data = WebhookPayload(**payload)
        logger.info("Webhook data validated successfully")
    except Exception as e:
        logger.warning(f"Invalid payload: {e}")
        logger.debug(
            f"Raw payload: {getattr(request.state, 'body', b'').decode() if hasattr(request.state, 'body') else '<no body cached>'}"
        )
        raise HTTPException(status_code=400, detail="Invalid payload")

    try:
        processed_comments = 0
        skipped_comments = 0

        for entry in webhook_data.entry:
            logger.debug(f"Processing entry: {entry.id}")
            for change in entry.changes:
                logger.debug(f"Processing change: {change.field}")
                if change.field == "comments":
                    comment_id = change.value.id
                    logger.info(f"Processing comment: {comment_id}")

                    # Debug: full webhook payload only at DEBUG level
                    logger.debug(
                        f"Webhook data for comment {comment_id}: {change.value.model_dump()}"
                    )

                    # Check if this is a reply and determine if it's from our bot or a user
                    if hasattr(change.value, "parent_id") and change.value.parent_id:
                        parent_id = change.value.parent_id
                        comment_username = change.value.from_.username
                        logger.debug(
                            f"Comment {comment_id} is a reply to parent {parent_id} from user: {comment_username}"
                        )

                        # Check if this comment is from our bot (by username)
                        if (
                            settings.instagram.bot_username
                            and comment_username == settings.instagram.bot_username
                        ):
                            logger.info(
                                f"Bot reply detected for comment {comment_id} ({comment_username}) - skipping to prevent loop"
                            )
                            skipped_comments += 1
                            continue

                        # Check if the parent comment was replied to by our bot (to prevent infinite loops)
                        parent_reply_check = await session.execute(
                            select(QuestionAnswer).where(
                                QuestionAnswer.reply_id == parent_id
                            )
                        )
                        if parent_reply_check.scalar_one_or_none():
                            logger.info(
                                f"Reply loop detected for comment {comment_id} to bot comment {parent_id} - skipping"
                            )
                            skipped_comments += 1
                            continue
                        else:
                            logger.debug(
                                f"Comment {comment_id} is user reply to {parent_id} - processing"
                            )

                    # Additional safety check: Check if this comment_id exists as a reply_id in our database
                    reply_check = await session.execute(
                        select(QuestionAnswer).where(
                            QuestionAnswer.reply_id == comment_id
                        )
                    )
                    if reply_check.scalar_one_or_none():
                        logger.info(
                            f"Own reply detected for {comment_id} via reply_id - skipping"
                        )
                        skipped_comments += 1
                        continue

                    # Log the decision for processing
                    logger.debug(
                        f"Comment {comment_id} passed loop checks - processing"
                    )

                    try:
                        # Check if comment already exists
                        existing_comment = await session.get(
                            InstagramComment, comment_id
                        )
                        if existing_comment:
                            logger.debug(
                                f"Comment {comment_id} already exists, checking classification"
                            )

                            # Если комментарий есть, но классификация не завершена - перезапускаем
                            if (
                                not existing_comment.classification
                                or existing_comment.classification.processing_status
                                != ProcessingStatus.COMPLETED
                            ):
                                classify_comment_task.delay(comment_id)
                                logger.info(
                                    f"Queued classification for existing comment {comment_id}"
                                )

                            skipped_comments += 1
                            continue

                        # Extract parent_id if present (for replies)
                        parent_id = None
                        if (
                            hasattr(change.value, "parent_id")
                            and change.value.parent_id
                        ):
                            parent_id = change.value.parent_id
                            logger.debug(
                                f"Comment {comment_id} is a reply to parent comment: {parent_id}"
                            )
                        else:
                            logger.debug(
                                f"Comment {comment_id} is a top-level comment (no parent)"
                            )

                        # Ensure media exists before creating comment
                        media_id = change.value.media.id
                        logger.debug(
                            f"Ensuring media {media_id} exists before creating comment"
                        )

                        from core.services.media_service import MediaService

                        media_service = MediaService()
                        media = await media_service.get_or_create_media(
                            media_id, session
                        )

                        if not media:
                            logger.error(
                                f"Failed to create/get media {media_id}, skipping comment {comment_id}"
                            )
                            skipped_comments += 1
                            continue

                        logger.info(f"Media {media_id} confirmed, creating comment")

                        # Create new comment
                        comment_data = {
                            "id": comment_id,
                            "media_id": change.value.media.id,
                            "user_id": change.value.from_.id,
                            "username": change.value.from_.username,
                            "text": change.value.text,
                            "created_at": datetime.datetime.fromtimestamp(entry.time),
                            "parent_id": parent_id,
                            "raw_data": change.value.model_dump(),
                        }

                        logger.debug(f"Creating comment with data: {comment_data}")
                        comment = InstagramComment(**comment_data)

                        # Создаем запись классификации
                        classification = CommentClassification(comment_id=comment_id)
                        comment.classification = classification

                        session.add(comment)
                        await session.commit()

                        # Ставим задачу классификации в Celery
                        classify_comment_task.delay(comment_id)

                        logger.info(
                            f"Comment {comment_id} saved; queued for classification"
                        )
                        processed_comments += 1

                    except IntegrityError as e:
                        await session.rollback()
                        logger.warning(
                            f"Comment {comment_id} already inserted by another process, skipping"
                        )
                        skipped_comments += 1
                        continue
                    except Exception as e:
                        await session.rollback()
                        logger.exception(f"Error processing comment {comment_id}")
                        logger.debug(f"Comment data: {change.value.model_dump()}")
                        continue

        logger.info(
            f"Webhook completed: {processed_comments} new, {skipped_comments} skipped"
        )
        return {
            "status": "ok",
            "processed": processed_comments,
            "skipped": skipped_comments,
        }

    except Exception as e:
        logger.exception("Unexpected error processing webhook")
        await session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
