import asyncio
import logging
import os
import redis
from datetime import datetime
from ..utils.time import now_db_utc
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import selectinload

from ..celery_app import celery_app
from ..config import settings

from ..models import QuestionAnswer, InstagramComment, AnswerStatus
from ..services.instagram_service import InstagramGraphAPIService

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
def send_instagram_reply_task(self, comment_id: str, answer_text: str):
    """Synchronous wrapper for asynchronous Instagram reply sending"""
    # Redis-based lock to prevent duplicate processing
    redis_client = redis.Redis.from_url(settings.celery.broker_url)
    lock_key = f"instagram_reply_lock:{comment_id}"

    # Try to acquire lock with 30 second timeout
    if not redis_client.set(lock_key, "processing", nx=True, ex=30):
        logger.info(f"Reply task for comment {comment_id} is already being processed, skipping")
        return {"status": "skipped", "reason": "already_processing"}

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(send_instagram_reply_async(comment_id, answer_text, self))
            return result
        finally:
            loop.close()
    finally:
        # Release the lock
        redis_client.delete(lock_key)


async def send_instagram_reply_async(comment_id: str, answer_text: str, task_instance=None):
    """Asynchronous task for sending Instagram private reply"""
    engine = create_async_engine(settings.db.url, echo=settings.db.echo)
    session_factory = async_sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    async with session_factory() as session:
        try:
            # Get the comment and its answer
            result = await session.execute(
                select(InstagramComment)
                .options(selectinload(InstagramComment.question_answer))
                .where(InstagramComment.id == comment_id)
            )
            comment = result.scalar_one_or_none()

            if not comment:
                logger.warning(f"Comment {comment_id} not found")
                return {"status": "error", "reason": "comment_not_found"}

            if not comment.question_answer:
                logger.warning(f"Comment {comment_id} has no answer")
                return {"status": "error", "reason": "no_answer"}

            # Check if answer is completed
            if comment.question_answer.processing_status != AnswerStatus.COMPLETED:
                logger.warning(f"Answer for comment {comment_id} is not completed yet")
                return {"status": "error", "reason": "answer_not_completed"}

            # Check if we already sent a reply (to avoid duplicate replies)
            if hasattr(comment.question_answer, "reply_sent") and comment.question_answer.reply_sent:
                logger.info(f"Reply already sent for comment {comment_id}")
                return {"status": "skipped", "reason": "reply_already_sent"}

            # Additional check: Look for existing reply_id to prevent duplicates
            if comment.question_answer.reply_id:
                logger.info(f"Reply already exists with ID {comment.question_answer.reply_id} for comment {comment_id}")
                return {"status": "skipped", "reason": "reply_id_already_exists"}

            # Final check before sending: Use atomic update to prevent race conditions
            # Try to atomically set a "processing" flag to prevent duplicate processing
            try:
                # Use an atomic update to set a processing flag
                update_result = await session.execute(
                    select(QuestionAnswer)
                    .where(
                        and_(
                            QuestionAnswer.comment_id == comment_id,
                            QuestionAnswer.reply_sent == False,
                            QuestionAnswer.reply_id.is_(None),
                        )
                    )
                    .with_for_update(skip_locked=True)
                )
                question_answer = update_result.scalar_one_or_none()

                if not question_answer:
                    logger.info(f"Comment {comment_id} already has a reply or is being processed by another worker")
                    return {"status": "skipped", "reason": "already_processed_or_processing"}

            except Exception as e:
                logger.warning(f"Failed to acquire lock for comment {comment_id}: {e}")
                return {"status": "skipped", "reason": "lock_acquisition_failed"}

            # Check if we're in development mode - skip actual Instagram API call
            development_mode = os.getenv("DEVELOPMENT_MODE", "false").lower() == "true"

            if development_mode:
                logger.info(f"DEVELOPMENT_MODE: Skipping Instagram API call for comment {comment_id}")
                # Simulate successful reply without actually calling Instagram API
                reply_result = {
                    "success": True,
                    "reply_id": f"test_reply_{comment_id}",
                    "response": {"test_mode": True, "message": "Reply skipped in development mode"},
                }
            else:
                # Initialize Instagram service
                instagram_service = InstagramGraphAPIService()
                # Send the reply to comment
                reply_result = await instagram_service.send_reply_to_comment(comment_id, answer_text)

            if reply_result["success"]:
                try:
                    # Mark reply as sent in the database
                    comment.question_answer.reply_sent = True
                    comment.question_answer.reply_sent_at = now_db_utc()
                    comment.question_answer.reply_status = "sent"
                    comment.question_answer.reply_response = reply_result.get("response", {})
                    reply_id = reply_result.get("reply_id")
                    comment.question_answer.reply_id = reply_id  # Store reply_id to prevent infinite loops

                    logger.info(f"Storing reply_id: {reply_id} for comment {comment_id}")

                    await session.commit()
                except Exception as e:
                    # Handle potential duplicate reply_id constraint violation
                    if "uq_question_answers_reply_id" in str(e) or "duplicate key" in str(e).lower():
                        logger.warning(f"Duplicate reply_id {reply_id} detected for comment {comment_id}, skipping")
                        return {"status": "skipped", "reason": "duplicate_reply_id_constraint"}
                    else:
                        raise e

                logger.info(f"Successfully sent Instagram reply for comment {comment_id}")
                return {"status": "success", "comment_id": comment_id, "reply_result": reply_result}
            else:
                # Log the error but don't mark as failed yet (might retry)
                logger.error(f"Failed to send Instagram reply for comment {comment_id}: {reply_result}")

                if task_instance and task_instance.request.retries < task_instance.max_retries:
                    # Use shorter retry intervals for Instagram API rate limiting
                    retry_countdown = min(2**task_instance.request.retries * 30, 300)  # Max 5 minutes
                    logger.warning(
                        f"Instagram API error for comment {comment_id}, retry {task_instance.request.retries + 1}/{task_instance.max_retries} in {retry_countdown}s"
                    )
                    raise task_instance.retry(
                        countdown=retry_countdown, exc=Exception(reply_result.get("error", "Unknown error"))
                    )

                # Mark as failed after max retries
                comment.question_answer.reply_status = "failed"
                comment.question_answer.reply_error = str(reply_result.get("error", "Unknown error"))
                await session.commit()

                return {
                    "status": "error",
                    "comment_id": comment_id,
                    "reason": reply_result.get("error", "Unknown error"),
                }

        except Exception as exc:
            logger.exception(f"Error sending Instagram reply for comment {comment_id}")
            await session.rollback()

            if task_instance and task_instance.request.retries < task_instance.max_retries:
                retry_countdown = 2**task_instance.request.retries * 60
                raise task_instance.retry(countdown=retry_countdown, exc=exc)

            return {"status": "error", "reason": str(exc)}
        finally:
            await engine.dispose()


@celery_app.task(bind=True, max_retries=3)
def process_pending_replies_task(self):
    """Periodic task for processing pending replies"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(process_pending_replies_async(self))
    finally:
        loop.close()


async def process_pending_replies_async(task_instance=None):
    """Process all completed answers that haven't been replied to yet"""
    # Ensure only one instance runs at a time across workers
    try:
        redis_client = redis.Redis.from_url(settings.celery.broker_url)
        lock_key = "process_pending_replies_lock"
        # TTL shorter than schedule interval to avoid overlap
        if not redis_client.set(lock_key, "1", nx=True, ex=240):
            logger.info("Another process_pending_replies is running; skipping this run")
            return {"status": "skipped", "reason": "already_running"}
    except Exception:
        logger.warning("Failed to acquire process_pending_replies lock; proceeding anyway")

    engine = create_async_engine(settings.db.url, echo=settings.db.echo)
    session_factory = async_sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    async with session_factory() as session:
        try:
            # Find completed answers that haven't been replied to
            stmt = select(QuestionAnswer).where(
                and_(
                    QuestionAnswer.processing_status == AnswerStatus.COMPLETED,
                    QuestionAnswer.answer.isnot(None),
                    QuestionAnswer.reply_sent == False,  # Assuming we'll add this field
                )
            )
            result = await session.execute(stmt)
            pending_answers = result.scalars().all()

            if not pending_answers:
                logger.info("No pending replies to process.")
                return {"status": "success", "message": "No pending replies to process"}

            logger.info(f"Processing {len(pending_answers)} pending replies.")
            processed_count = 0
            results = []

            for answer_record in pending_answers:
                try:
                    # Send the reply
                    reply_result = await send_instagram_reply_async(answer_record.comment_id, answer_record.answer)
                    results.append(
                        {"comment_id": answer_record.comment_id, "status": "success", "result": reply_result}
                    )
                    processed_count += 1
                    logger.info(f"Processed reply for comment {answer_record.comment_id}")
                except Exception as e:
                    results.append({"comment_id": answer_record.comment_id, "status": "error", "error": str(e)})
                    logger.error(f"Failed to process reply for comment {answer_record.comment_id}: {e}")

            return {
                "status": "success",
                "processed_count": processed_count,
                "total_found": len(pending_answers),
                "results": results,
            }

        except Exception as e:
            logger.error(f"Error in process_pending_replies: {e}")
            await session.rollback()
            return {"status": "error", "reason": str(e)}
        finally:
            await engine.dispose()
            # Release lock by letting TTL expire; ensure key removed if we created it without TTL
            try:
                if "redis_client" in locals():
                    # Keep it simple; delete if still present
                    redis_client.delete("process_pending_replies_lock")
            except Exception:
                pass
