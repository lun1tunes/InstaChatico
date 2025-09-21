import datetime
import json
import logging

from fastapi import APIRouter, HTTPException, status, Depends, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from core.models import db_helper
from core.config import settings
from core.models.instagram_comment import InstagramComment
from . import crud
from .schemas import WebhookPayload

logging.basicConfig(level=logging.INFO)
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


@router.post("/")
async def process_webhook(request: Request, session: AsyncSession = Depends(db_helper.scoped_session_dependency)):
    try:
        logger.info("Processing webhook request")
        payload = json.loads(request.state.body.decode())
        logger.info(f"Parsed payload: {payload}")
        webhook_data = WebhookPayload(**payload)
        logger.info("Webhook data validated successfully")
    except Exception as e:
        logger.error(f"Invalid payload: {e}")
        logger.error(f"Raw payload: {request.state.body.decode()}")
        raise HTTPException(status_code=400, detail="Invalid payload")

    try:
        processed_comments = 0
        skipped_comments = 0
        
        for entry in webhook_data.entry:
            logger.info(f"Processing entry: {entry.id}")
            for change in entry.changes:
                logger.info(f"Processing change: {change.field}")
                if change.field == "comments":
                    comment_id = change.value.id
                    logger.info(f"Processing comment: {comment_id}")
                    
                    try:
                        # Check if comment already exists
                        existing_comment = await session.get(InstagramComment, comment_id)
                        if existing_comment:
                            logger.info(f"Comment {comment_id} already exists, skipping")
                            skipped_comments += 1
                            continue
                        
                        # Create new comment with error handling for missing fields
                        comment_data = {
                            "id": comment_id,
                            "media_id": change.value.media.id,
                            "user_id": change.value.from_.id,
                            "username": change.value.from_.username,
                            "text": change.value.text,
                            "created_at": datetime.datetime.fromtimestamp(entry.time),
                            "raw_data": change.value.model_dump()
                        }
                        
                        logger.info(f"Creating comment with data: {comment_data}")
                        comment = InstagramComment(**comment_data)
                        
                        session.add(comment)
                        await session.commit()
                        logger.info(f"Comment {comment_id} saved successfully")
                        processed_comments += 1
                        
                    except IntegrityError as e:
                        # Handle race condition where comment was inserted between check and insert
                        await session.rollback()
                        logger.info(f"Comment {comment_id} was inserted by another process, skipping")
                        skipped_comments += 1
                        continue
                    except Exception as e:
                        # Handle any other errors in comment processing
                        await session.rollback()
                        logger.error(f"Error processing comment {comment_id}: {e}")
                        logger.error(f"Comment data: {change.value.model_dump()}")
                        continue

        logger.info(f"Webhook processing completed: {processed_comments} new comments, {skipped_comments} duplicates skipped")
        return {"status": "ok", "processed": processed_comments, "skipped": skipped_comments}
        
    except Exception as e:
        logger.error(f"Unexpected error processing webhook: {e}")
        await session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")