"""
Telegram API endpoints for testing and management
"""

import logging
from fastapi import APIRouter, HTTPException
from core.logging_config import trace_id_ctx
from core.services.telegram_alert_service import TelegramAlertService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["Telegram"])


@router.get("/test-connection")
async def test_telegram_bot_connection():
    """Test Telegram bot connection and configuration"""
    try:
        telegram_service = TelegramAlertService()
        result = await telegram_service.test_connection()

        if result.get("success"):
            return {
                "status": "success",
                "message": "Telegram bot connection successful",
                "bot_info": result.get("bot_info"),
                "chat_id": result.get("chat_id"),
            }
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Telegram connection failed: {result.get('error')}",
            )
    except Exception as e:
        logger.error(f"Error testing Telegram connection: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.post("/test-notification")
async def test_telegram_notification():
    """Send a test notification to Telegram"""
    try:
        # Create test comment data
        test_comment_data = {
            "comment_id": "test_12345",
            "comment_text": "This is a test urgent issue comment for testing Telegram notifications.",
            "classification": "urgent issue / complaint",
            "confidence": 95,
            "reasoning": "Test notification to verify Telegram integration is working correctly.",
            "sentiment_score": -80,
            "toxicity_score": 20,
            "media_id": "test_media_123",
            "username": "test_user",
            "timestamp": "2024-01-01T12:00:00Z",
        }

        telegram_service = TelegramAlertService()
        result = await telegram_service.send_urgent_issue_notification(test_comment_data)

        if result.get("success"):
            return {
                "status": "success",
                "message": "Test notification sent successfully",
                "telegram_message_id": result.get("message_id"),
                "response": result.get("response"),
            }
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to send test notification: {result.get('error')}",
            )
    except Exception as e:
        logger.error(f"Error sending test notification: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.post("/test-log-alert")
async def test_log_alert(level: str = "warning"):
    """Emit a test log at the given level to verify Telegram log alerts.
    Levels: debug, info, warning, error, critical
    """
    level = level.lower().strip()
    trace_id = trace_id_ctx.get()
    try:
        if level == "debug":
            logger.debug("Test log alert: DEBUG level")
        elif level == "info":
            logger.info("Test log alert: INFO level")
        elif level == "warning":
            logger.warning("Test log alert: WARNING level")
        elif level == "error":
            logger.exception("Test log alert: ERROR level with exception")
        elif level == "critical":
            logger.exception("Test log alert: CRITICAL level with exception")
        else:
            raise HTTPException(
                status_code=400,
                detail="Invalid level. Use: debug|info|warning|error|critical",
            )
    except Exception as e:
        logger.exception("Failed to emit test log alert")
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "emitted", "level": level, "trace_id": trace_id}
