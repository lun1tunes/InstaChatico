"""
Telegram Notification Tasks

This module contains Celery tasks for sending notifications to Telegram
when Instagram comments are classified as urgent issues or critical feedback.
"""

import asyncio
import logging
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import selectinload

from ..celery_app import celery_app
from ..models import InstagramComment, CommentClassification
from ..services.telegram_alert_service import TelegramAlertService
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
    """Async task to send notification to Telegram for urgent issues or critical feedback"""

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

            # Check if this comment requires a Telegram notification
            classification = comment.classification.classification
            notify_classifications = [
                "urgent issue / complaint",
                "critical feedback",
                "partnership proposal",
                # Note: "toxic / abusive" is NOT notified - we ignore such comments
            ]
            if classification not in notify_classifications:
                logger.info(
                    f"Comment {comment_id} classification '{classification}' does not require Telegram notification"
                )
                return {"status": "skipped", "reason": "no_notification_needed"}

            # Prepare comment data for Telegram notification
            comment_data = {
                "comment_id": comment.id,
                "comment_text": comment.text,
                "classification": comment.classification.classification,
                "confidence": comment.classification.confidence,
                "reasoning": comment.classification.reasoning,
                "sentiment_score": comment.classification.meta_data.get("sentiment_score", 0),
                "toxicity_score": comment.classification.meta_data.get("toxicity_score", 0),
                "media_id": comment.media_id,
                "username": comment.username or "Unknown user",
                "timestamp": comment.created_at.isoformat() if comment.created_at else "Unknown time",
            }

            # Send Telegram notification
            telegram_service = TelegramAlertService(alert_type="instagram_comment_alerts")
            notification_result = await telegram_service.send_notification(comment_data)

            if notification_result.get("success"):
                logger.info(f"Telegram notification sent successfully for comment {comment_id}")
                return {
                    "status": "success",
                    "comment_id": comment_id,
                    "telegram_message_id": notification_result.get("message_id"),
                    "notification_result": notification_result,
                }
            else:
                logger.error(
                    f"Failed to send Telegram notification for comment {comment_id}: {notification_result.get('error')}"
                )

                # Retry if we haven't exceeded max retries
                if task_instance and task_instance.request.retries < task_instance.max_retries:
                    retry_countdown = 2**task_instance.request.retries * 60
                    raise task_instance.retry(
                        countdown=retry_countdown, exc=Exception(notification_result.get("error"))
                    )

                return {
                    "status": "error",
                    "comment_id": comment_id,
                    "reason": notification_result.get("error"),
                    "notification_result": notification_result,
                }

        except Exception as exc:
            logger.exception(f"Error sending Telegram notification for comment {comment_id}")

            # Retry if we haven't exceeded max retries
            if task_instance and task_instance.request.retries < task_instance.max_retries:
                retry_countdown = 2**task_instance.request.retries * 60
                raise task_instance.retry(countdown=retry_countdown, exc=exc)

            return {"status": "error", "comment_id": comment_id, "reason": str(exc)}
        finally:
            await engine.dispose()
