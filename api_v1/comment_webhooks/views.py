import datetime
import json
import logging

from fastapi import APIRouter, HTTPException, status, Depends, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import db_helper
from core.config import settings
from core.models.instagram_comment import InstagramComment
from . import crud
from .schemas import WebhookPayload, WebhookVerification

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(tags=["Webhooks"])

@router.get("/")
async def webhook_verification(params: WebhookVerification = Depends()):
    if params.hub_verify_token != settings.app_webhook_verify_token:
        raise HTTPException(status_code=403, detail="Invalid verify token")
    
    logger.info(f"Verification completed successfully")
    return PlainTextResponse(params.hub_challenge)


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
        raise HTTPException(status_code=400, detail="Invalid payload")

    try:
        for entry in webhook_data.entry:
            logger.info(f"Processing entry: {entry.id}")
            for change in entry.changes:
                logger.info(f"Processing change: {change.field}")
                if change.field == "comments":
                    logger.info(f"Creating comment: {change.value.id}")
                    comment = InstagramComment(
                        id=change.value.id,
                        media_id=change.value.media.id,
                        user_id=change.value.from_.id,
                        username=change.value.from_.username,
                        text=change.value.text,
                        created_at=datetime.datetime.fromtimestamp(entry.time),
                        raw_data=change.value.model_dump()
                    )
                    
                    session.add(comment)
                    await session.commit()
                    logger.info(f"Comment {change.value.id} saved successfully")

        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Database error: {e}")
        await session.rollback()
        raise HTTPException(status_code=500, detail="Database error")