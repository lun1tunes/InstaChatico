"""Instagram webhook endpoints for comment processing."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.logging_config import trace_id_ctx
from core.models import db_helper
from core.models.comment_classification import CommentClassification, ProcessingStatus
from core.models.instagram_comment import InstagramComment
from core.services.media_service import MediaService
from core.tasks.classification_tasks import classify_comment_task

from .helpers import extract_comment_data, get_existing_comment, should_skip_comment
from .schemas import WebhookPayload

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Webhooks"])


@router.get("/")
async def webhook_verification(request: Request):
    """Handle Instagram webhook verification challenge."""
    hub_mode = request.query_params.get("hub.mode")
    hub_challenge = request.query_params.get("hub.challenge")
    hub_verify_token = request.query_params.get("hub.verify_token")

    if not all([hub_mode, hub_challenge, hub_verify_token]):
        raise HTTPException(status_code=422, detail="Missing required parameters")

    if hub_verify_token != settings.app_webhook_verify_token:
        raise HTTPException(status_code=403, detail="Invalid verify token")

    logger.info("Webhook verification successful")
    return PlainTextResponse(hub_challenge)


@router.post("")
@router.post("/")
async def process_webhook(
    webhook_data: WebhookPayload,
    request: Request,
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
):
    """Process Instagram webhook for new comments."""
    # Bind trace ID early if provided
    if incoming_trace := request.headers.get("X-Trace-Id"):
        trace_id_ctx.set(incoming_trace)

    logger.info("Processing webhook request")

    processed_count = 0
    skipped_count = 0

    try:
        # Use Pydantic helper to extract all comments
        comments = webhook_data.get_all_comments()
        logger.info(f"Webhook received {len(comments)} comment(s)")

        for entry, comment in comments:
            comment_id = comment.id

            try:
                # Check if comment should be skipped (bot loops, etc.)
                should_skip, skip_reason = await should_skip_comment(comment, session)
                if should_skip:
                    logger.info(f"Skipping comment {comment_id}: {skip_reason}")
                    skipped_count += 1
                    continue

                # Check if comment already exists
                existing = await get_existing_comment(comment_id, session)
                if existing:
                    logger.debug(f"Comment {comment_id} already exists")

                    # Re-queue classification if incomplete
                    if (
                        not existing.classification
                        or existing.classification.processing_status
                        != ProcessingStatus.COMPLETED
                    ):
                        classify_comment_task.delay(comment_id)
                        logger.info(f"Re-queued classification for {comment_id}")

                    skipped_count += 1
                    continue

                # Ensure media exists
                media_service = MediaService()
                media = await media_service.get_or_create_media(
                    comment.media.id, session
                )
                if not media:
                    logger.error(f"Failed to create media {comment.media.id}")
                    skipped_count += 1
                    continue

                # Create comment record
                comment_data = extract_comment_data(comment, entry.time)
                new_comment = InstagramComment(**comment_data)
                new_comment.classification = CommentClassification(
                    comment_id=comment_id
                )

                session.add(new_comment)
                await session.commit()

                # Queue for classification
                classify_comment_task.delay(comment_id)
                logger.info(f"Comment {comment_id} saved and queued for classification")
                processed_count += 1

            except IntegrityError:
                await session.rollback()
                logger.warning(f"Comment {comment_id} inserted by another process")
                skipped_count += 1
            except Exception:
                await session.rollback()
                logger.exception(f"Error processing comment {comment_id}")
                skipped_count += 1

        logger.info(f"Webhook complete: {processed_count} new, {skipped_count} skipped")
        return {
            "status": "ok",
            "processed": processed_count,
            "skipped": skipped_count,
        }

    except Exception:
        logger.exception("Unexpected error processing webhook")
        await session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
