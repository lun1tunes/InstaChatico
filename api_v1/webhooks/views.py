"""
Webhook API views - clean route handlers with proper separation of concerns.
Only contains FastAPI route definitions and request/response handling.
"""

import json
import time
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.simple_dependencies import get_db_session, get_classification_service
from core.models.comment_classification import ProcessingStatus
from core.logging_config import get_logger
from core.exceptions import WebhookValidationError, WebhookProcessingError

from .schemas import (
    WebhookVerificationParams,
    WebhookPayload,
    WebhookProcessingResult,
    WebhookHealthStatus
)
from .crud import webhook_crud

logger = get_logger(__name__, "webhook_views")
router = APIRouter(tags=["Webhooks"])


@router.get("/")
async def webhook_verification(request: Request):
    """
    Handle Instagram webhook verification.
    
    Instagram sends a GET request with verification parameters
    that we need to validate and echo back the challenge.
    """
    try:
        # Extract and validate parameters
        params = WebhookVerificationParams(
            **{
                "hub.mode": request.query_params.get("hub.mode"),
                "hub.challenge": request.query_params.get("hub.challenge"),
                "hub.verify_token": request.query_params.get("hub.verify_token")
            }
        )
        
        # Verify token matches our configuration
        if params.hub_verify_token != settings.app_webhook_verify_token:
            logger.warning(
                "Invalid webhook verify token",
                extra_fields={"provided_token": params.hub_verify_token[:10] + "..."},
                operation="webhook_verification"
            )
            raise HTTPException(status_code=403, detail="Invalid verify token")
        
        logger.info(
            "Webhook verification successful",
            extra_fields={"challenge": params.hub_challenge[:10] + "..."},
            operation="webhook_verification"
        )
        
        return PlainTextResponse(params.hub_challenge)
        
    except ValueError as e:
        logger.error(
            "Webhook verification failed - invalid parameters",
            extra_fields={"error": str(e)},
            operation="webhook_verification"
        )
        raise HTTPException(status_code=422, detail=f"Invalid parameters: {str(e)}")
    except Exception as e:
        logger.error(
            "Webhook verification failed - unexpected error",
            extra_fields={"error": str(e)},
            operation="webhook_verification"
        )
        raise HTTPException(status_code=500, detail="Verification failed")


@router.post("/", response_model=WebhookProcessingResult)
async def process_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    classification_service = Depends(get_classification_service)
) -> WebhookProcessingResult:
    """
    Process Instagram webhook payload.
    
    Receives comment events from Instagram and processes them:
    1. Validates payload structure
    2. Stores comments in database
    3. Triggers AI classification
    4. Returns processing results
    """
    start_time = time.time()
    
    try:
        # Parse and validate webhook payload
        body_bytes = getattr(request.state, "body", None) or await request.body()
        payload_data = json.loads(body_bytes.decode())
        
        logger.info(
            "Received webhook payload",
            extra_fields={"payload_size": len(body_bytes)},
            operation="process_webhook"
        )
        
        # Validate with Pydantic
        payload = WebhookPayload(**payload_data)
        
        # Process all entries and changes
        processed = 0
        skipped = 0
        errors = 0
        
        for entry in payload.entry:
            for change in entry.changes:
                if change.field == "comments":
                    try:
                        result = await _process_single_comment(
                            change.value,
                            entry.time,
                            session,
                            classification_service
                        )
                        
                        if result == "processed":
                            processed += 1
                        elif result == "skipped":
                            skipped += 1
                        else:
                            errors += 1
                            
                    except Exception as e:
                        logger.error(
                            "Failed to process comment",
                            extra_fields={
                                "comment_id": change.value.id,
                                "error": str(e)
                            },
                            operation="process_webhook"
                        )
                        errors += 1
        
        processing_time_ms = int((time.time() - start_time) * 1000)
        
        logger.info(
            "Webhook processing completed",
            extra_fields={
                "processed": processed,
                "skipped": skipped,
                "errors": errors,
                "processing_time_ms": processing_time_ms
            },
            operation="process_webhook"
        )
        
        return WebhookProcessingResult(
            status="success" if errors == 0 else "partial_success",
            processed=processed,
            skipped=skipped,
            errors=errors,
            message=f"Processed {processed} comments, skipped {skipped}, errors {errors}",
            processing_time_ms=processing_time_ms
        )
        
    except json.JSONDecodeError as e:
        logger.error(
            "Invalid JSON in webhook payload",
            extra_fields={"error": str(e)},
            operation="process_webhook"
        )
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    except ValueError as e:
        logger.error(
            "Invalid webhook payload structure",
            extra_fields={"error": str(e)},
            operation="process_webhook"
        )
        raise HTTPException(status_code=422, detail=f"Invalid payload: {str(e)}")
    except Exception as e:
        logger.error(
            "Webhook processing failed",
            extra_fields={"error": str(e)},
            operation="process_webhook"
        )
        raise HTTPException(status_code=500, detail="Processing failed")


async def _process_single_comment(
    comment_value,
    timestamp: int,
    session: AsyncSession,
    classification_service
) -> str:
    """
    Process a single comment from webhook.
    
    Args:
        comment_value: Comment data from webhook
        timestamp: Unix timestamp from webhook
        session: Database session
        classification_service: AI classification service
        
    Returns:
        Processing result: "processed", "skipped", or "error"
    """
    comment_id = comment_value.id
    
    try:
        # Skip replies to prevent infinite loops
        if comment_value.parent_id:
            logger.info(
                f"Skipping reply comment {comment_id}",
                operation="process_single_comment"
            )
            return "skipped"
        
        # Check if this is our own reply
        if await webhook_crud.check_if_reply(session, comment_id):
            return "skipped"
        
        # Check if comment already exists
        existing_comment = await webhook_crud.get_comment(session, comment_id)
        if existing_comment:
            logger.info(
                f"Comment {comment_id} already exists",
                operation="process_single_comment"
            )
            return "skipped"
        
        # Create comment record
        comment_data = {
            "id": comment_id,
            "media_id": comment_value.media.id,
            "user_id": comment_value.from_.id,
            "username": comment_value.from_.username,
            "text": comment_value.text,
            "created_at": datetime.fromtimestamp(timestamp),
            "raw_data": comment_value.model_dump()
        }
        
        await webhook_crud.create_comment(session, comment_data)
        
        # Create classification record
        await webhook_crud.create_classification(session, comment_id)
        
        # Trigger AI classification
        try:
            classification_result = await classification_service.classify_comment(
                comment_value.text
            )
            
            # Update classification with results
            classification_data = {
                "classification": classification_result["classification"],
                "confidence": classification_result["confidence"],
                "processing_status": ProcessingStatus.COMPLETED,
                "processing_completed_at": datetime.utcnow(),
                "meta_data": {
                    "contains_question": classification_result.get("contains_question"),
                    "sentiment_score": classification_result.get("sentiment_score"),
                    "toxicity_score": classification_result.get("toxicity_score")
                }
            }
            
            await webhook_crud.update_classification(
                session, comment_id, classification_data
            )
            
            logger.log_classification_completed(
                comment_id,
                classification_result["classification"],
                classification_result["confidence"],
                classification_result.get("processing_time_ms", 0)
            )
            
        except Exception as e:
            logger.error(
                f"Classification failed for comment {comment_id}",
                extra_fields={"error": str(e)},
                operation="process_single_comment"
            )
            
            # Update classification as failed
            await webhook_crud.update_classification(
                session,
                comment_id,
                {
                    "processing_status": ProcessingStatus.FAILED,
                    "last_error": str(e)
                }
            )
        
        return "processed"
        
    except Exception as e:
        logger.error(
            f"Failed to process comment {comment_id}",
            extra_fields={"error": str(e)},
            operation="process_single_comment"
        )
        return "error"


@router.get("/health", response_model=WebhookHealthStatus)
async def webhook_health(
    session: AsyncSession = Depends(get_db_session)
) -> WebhookHealthStatus:
    """
    Health check endpoint for webhook service.
    
    Returns current status and basic statistics.
    """
    try:
        # Get processing stats
        stats = await webhook_crud.get_processing_stats(session)
        
        return WebhookHealthStatus(
            status="healthy",
            service="webhook_processor",
            timestamp=datetime.utcnow(),
            details=stats
        )
        
    except Exception as e:
        logger.error(
            "Webhook health check failed",
            extra_fields={"error": str(e)},
            operation="webhook_health"
        )
        
        return WebhookHealthStatus(
            status="unhealthy",
            service="webhook_processor",
            timestamp=datetime.utcnow(),
            details={"error": str(e)}
        )
