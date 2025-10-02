"""Instagram webhook endpoints for comment processing."""

import logging
import os
from datetime import datetime

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
from core.models.media import Media
from core.schemas.webhook import WebhookProcessingResponse, TestCommentResponse
from core.services.media_service import MediaService
from core.tasks.answer_tasks import generate_answer_async
from core.tasks.classification_tasks import classify_comment_async, classify_comment_task

from .helpers import extract_comment_data, get_existing_comment, should_skip_comment
from .schemas import TestCommentPayload, WebhookPayload

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
                        or existing.classification.processing_status != ProcessingStatus.COMPLETED
                    ):
                        classify_comment_task.delay(comment_id)
                        logger.info(f"Re-queued classification for {comment_id}")

                    skipped_count += 1
                    continue

                # Ensure media exists
                media_service = MediaService()
                media = await media_service.get_or_create_media(comment.media.id, session)
                if not media:
                    logger.error(f"Failed to create media {comment.media.id}")
                    skipped_count += 1
                    continue

                # Create comment record
                comment_data = extract_comment_data(comment, entry.time)
                new_comment = InstagramComment(**comment_data)
                new_comment.classification = CommentClassification(comment_id=comment_id)

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
        return WebhookProcessingResponse(
            status="success",
            message=f"Processed {processed_count} new comments, skipped {skipped_count}",
        )

    except Exception:
        logger.exception("Unexpected error processing webhook")
        await session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/test", tags=["Testing"])
async def test_comment_processing(
    test_data: TestCommentPayload,
    session: AsyncSession = Depends(db_helper.scoped_session_dependency),
):
    """
    Test endpoint for Instagram comment processing (DEVELOPMENT_MODE only).

    This endpoint processes comments through the full pipeline (classification → answer generation)
    but returns the answer in the response instead of posting to Instagram.
    All database records are created as in production mode.

    Only accessible when dev mode is enabled.
    """
    # Check if development mode is enabled
    development_mode = os.getenv("DEVELOPMENT_MODE", "false").lower() == "true"
    if not development_mode:
        raise HTTPException(status_code=403, detail="Test endpoint only accessible in dev mode")

    logger.info(f"Processing test comment: {test_data.comment_id}")

    try:
        # Step 1: Create or get media
        media_service = MediaService()

        # Check if media exists, if not create a test media record
        media_result = await session.execute(select(Media).where(Media.id == test_data.media_id))
        media = media_result.scalar_one_or_none()

        if not media:
            media = Media(
                id=test_data.media_id,
                permalink=f"https://instagram.com/p/test_{test_data.media_id}/",
                caption=test_data.media_caption or "Test media caption",
                media_url=test_data.media_url,
                media_type="IMAGE",
                username="test_user",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            session.add(media)
            await session.commit()
            logger.info(f"Created test media: {test_data.media_id}")

        # Step 2: Create or update comment
        existing_comment = await get_existing_comment(test_data.comment_id, session)

        if existing_comment:
            logger.info(f"Test comment {test_data.comment_id} already exists, will process anyway")
            comment = existing_comment
            # Update comment text if changed
            comment.text = test_data.text
            comment.parent_id = test_data.parent_id
        else:
            comment = InstagramComment(
                id=test_data.comment_id,
                media_id=test_data.media_id,
                user_id=test_data.user_id,
                username=test_data.username,
                text=test_data.text,
                parent_id=test_data.parent_id,
                created_at=datetime.utcnow(),
                raw_data={"test": True},
            )
            session.add(comment)
            logger.info(f"Created test comment: {test_data.comment_id}")

        # Step 3: Create or get classification record
        if not existing_comment or not existing_comment.classification:
            classification = CommentClassification(
                comment_id=test_data.comment_id,
                processing_status=ProcessingStatus.PENDING,
            )
            session.add(classification)

        await session.commit()

        # Step 4: Run classification (synchronously for testing)
        logger.info(f"Running classification for test comment {test_data.comment_id}")
        classification_result = await classify_comment_async(test_data.comment_id, task_instance=None)

        if classification_result.get("status") == "error":
            raise HTTPException(status_code=500, detail=f"Classification failed: {classification_result.get('reason')}")

        # Step 5: Check if it's a question
        classification_type = classification_result.get("classification", "").lower()
        logger.info(f"Test comment classified as: {classification_type}")

        # Get reasoning from database
        comment_with_class = await session.execute(
            select(InstagramComment).where(InstagramComment.id == test_data.comment_id)
        )
        comment_obj = comment_with_class.scalar_one_or_none()
        reasoning = None
        if comment_obj and hasattr(comment_obj, "classification") and comment_obj.classification:
            reasoning = comment_obj.classification.reasoning

        # Prepare processing details
        processing_details = {"classification_result": classification_result}
        answer_text = None

        # Step 6: If it's a question, generate answer
        if classification_type == "question / inquiry":
            logger.info(f"Generating answer for test question {test_data.comment_id}")
            answer_result = await generate_answer_async(test_data.comment_id, task_instance=None)

            if answer_result.get("status") == "error":
                processing_details["answer_error"] = answer_result.get("reason")
            else:
                answer_text = answer_result.get("answer")
                processing_details["answer_result"] = answer_result

            logger.info(f"Test comment processing complete. Answer generated: {bool(answer_result.get('answer'))}")
        else:
            logger.info(f"Test comment is not a question, skipping answer generation")

        return TestCommentResponse(
            status="success",
            message=f"Test comment processed: {classification_type}",
            comment_id=test_data.comment_id,
            classification=classification_result.get("classification"),
            answer=answer_text,
            processing_details=processing_details,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error processing test comment {test_data.comment_id}")
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Error processing test comment: {str(e)}")
