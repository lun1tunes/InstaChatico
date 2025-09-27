"""
Telegram Notification Tasks

This module contains Celery tasks for sending urgent issue notifications
to Telegram when Instagram comments are classified as urgent issues.
"""

import asyncio
import logging
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import selectinload

from ..celery_app import celery_app
from ..models import InstagramComment, CommentClassification
from ..services.telegram_service import TelegramService
from ..config import settings

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, max_retries=3)
def send_telegram_notification_task(self, comment_id: str):
    """Synchronous wrapper for async Telegram notification task"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(send_telegram_notification_async(comment_id, self))
    finally:
        loop.close()

async def send_telegram_notification_async(comment_id: str, task_instance=None):
    """Async task to send urgent issue notification to Telegram"""
    
    # Create a fresh engine and session for this task
    engine = create_async_engine(settings.db.url, echo=settings.db.echo)
    session_factory = async_sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    
    async with session_factory() as session:
        try:
            # Get the comment with its classification
            result = await session.execute(
                select(InstagramComment)
                .options(selectinload(InstagramComment.classification))
                .where(InstagramComment.id == comment_id)
            )
            comment = result.scalar_one_or_none()
            
            if not comment:
                logger.warning(f"Comment {comment_id} not found for Telegram notification")
                return {"status": "error", "reason": "comment_not_found"}
            
            if not comment.classification:
                logger.warning(f"No classification found for comment {comment_id}")
                return {"status": "error", "reason": "no_classification"}
            
            # Check if this is actually an urgent issue
            if comment.classification.classification != "urgent issue / complaint":
                logger.info(f"Comment {comment_id} is not urgent, skipping Telegram notification")
                return {"status": "skipped", "reason": "not_urgent"}
            
            # Prepare comment data for Telegram notification
            comment_data = {
                "comment_id": comment.id,
                "comment_text": comment.text,
                "classification": comment.classification.classification,
                "confidence": comment.classification.confidence,
                "reasoning": comment.classification.meta_data.get('reasoning', 'No reasoning available'),
                "sentiment_score": comment.classification.meta_data.get('sentiment_score', 0),
                "toxicity_score": comment.classification.meta_data.get('toxicity_score', 0),
                "media_id": comment.media_id,
                "username": comment.username or "Unknown user",
                "timestamp": comment.created_at.isoformat() if comment.created_at else "Unknown time"
            }
            
            # Send Telegram notification
            telegram_service = TelegramService()
            notification_result = telegram_service.send_urgent_issue_notification(comment_data)
            
            if notification_result.get("success"):
                logger.info(f"Telegram notification sent successfully for comment {comment_id}")
                return {
                    "status": "success",
                    "comment_id": comment_id,
                    "telegram_message_id": notification_result.get("message_id"),
                    "notification_result": notification_result
                }
            else:
                logger.error(f"Failed to send Telegram notification for comment {comment_id}: {notification_result.get('error')}")
                
                # Retry if we haven't exceeded max retries
                if task_instance and task_instance.request.retries < task_instance.max_retries:
                    retry_countdown = 2 ** task_instance.request.retries * 60
                    raise task_instance.retry(countdown=retry_countdown, exc=Exception(notification_result.get('error')))
                
                return {
                    "status": "error",
                    "comment_id": comment_id,
                    "reason": notification_result.get('error'),
                    "notification_result": notification_result
                }
                
        except Exception as exc:
            logger.error(f"Error sending Telegram notification for comment {comment_id}: {exc}")
            
            # Retry if we haven't exceeded max retries
            if task_instance and task_instance.request.retries < task_instance.max_retries:
                retry_countdown = 2 ** task_instance.request.retries * 60
                raise task_instance.retry(countdown=retry_countdown, exc=exc)
            
            return {
                "status": "error",
                "comment_id": comment_id,
                "reason": str(exc)
            }
        finally:
            await engine.dispose()

@celery_app.task
def test_telegram_connection():
    """Test task to verify Telegram bot connection"""
    try:
        telegram_service = TelegramService()
        result = telegram_service.test_connection()
        
        if result.get("success"):
            logger.info("Telegram connection test successful")
            return {
                "status": "success",
                "bot_info": result.get("bot_info"),
                "chat_id": result.get("chat_id")
            }
        else:
            logger.error(f"Telegram connection test failed: {result.get('error')}")
            return {
                "status": "error",
                "reason": result.get("error")
            }
    except Exception as e:
        logger.error(f"Error testing Telegram connection: {e}")
        return {
            "status": "error",
            "reason": str(e)
        }
