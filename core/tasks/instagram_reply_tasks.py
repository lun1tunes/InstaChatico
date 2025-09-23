import asyncio
import logging
from datetime import datetime
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import selectinload

from celery import Celery
from ..config import settings

# Create a separate celery app instance to avoid circular imports
celery_app = Celery(
    'instagram_classifier',
    broker=settings.celery.broker_url,
    backend=settings.celery.result_backend,
)

from ..models import QuestionAnswer, InstagramComment, AnswerStatus
from ..services.instagram_service import InstagramGraphAPIService

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, max_retries=3)
def send_instagram_reply_task(self, comment_id: str, answer_text: str):
    """Synchronous wrapper for asynchronous Instagram reply sending"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(send_instagram_reply_async(comment_id, answer_text, self))
    finally:
        loop.close()

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
            if hasattr(comment.question_answer, 'reply_sent') and comment.question_answer.reply_sent:
                logger.info(f"Reply already sent for comment {comment_id}")
                return {"status": "skipped", "reason": "reply_already_sent"}

            # Initialize Instagram service
            instagram_service = InstagramGraphAPIService()
            
            # Send the reply to comment
            reply_result = await instagram_service.send_reply_to_comment(comment_id, answer_text)
            
            if reply_result["success"]:
                # Mark reply as sent in the database
                comment.question_answer.reply_sent = True
                comment.question_answer.reply_sent_at = datetime.utcnow()
                comment.question_answer.reply_status = "sent"
                comment.question_answer.reply_response = reply_result.get("response", {})
                
                await session.commit()
                
                logger.info(f"Successfully sent Instagram reply for comment {comment_id}")
                return {
                    "status": "success",
                    "comment_id": comment_id,
                    "reply_result": reply_result
                }
            else:
                # Log the error but don't mark as failed yet (might retry)
                logger.error(f"Failed to send Instagram reply for comment {comment_id}: {reply_result}")
                
                if task_instance and task_instance.request.retries < task_instance.max_retries:
                    retry_countdown = 2 ** task_instance.request.retries * 60
                    raise task_instance.retry(countdown=retry_countdown, exc=Exception(reply_result.get("error", "Unknown error")))
                
                # Mark as failed after max retries
                comment.question_answer.reply_status = "failed"
                comment.question_answer.reply_error = str(reply_result.get("error", "Unknown error"))
                await session.commit()
                
                return {
                    "status": "error",
                    "comment_id": comment_id,
                    "reason": reply_result.get("error", "Unknown error")
                }

        except Exception as exc:
            logger.error(f"Error sending Instagram reply for comment {comment_id}: {exc}")
            await session.rollback()

            if task_instance and task_instance.request.retries < task_instance.max_retries:
                retry_countdown = 2 ** task_instance.request.retries * 60
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
    engine = create_async_engine(settings.db.url, echo=settings.db.echo)
    session_factory = async_sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    async with session_factory() as session:
        try:
            # Find completed answers that haven't been replied to
            stmt = select(QuestionAnswer).where(
                and_(
                    QuestionAnswer.processing_status == AnswerStatus.COMPLETED,
                    QuestionAnswer.answer.isnot(None),
                    QuestionAnswer.reply_sent == False  # Assuming we'll add this field
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
                    results.append({
                        "comment_id": answer_record.comment_id, 
                        "status": "success", 
                        "result": reply_result
                    })
                    processed_count += 1
                    logger.info(f"Processed reply for comment {answer_record.comment_id}")
                except Exception as e:
                    results.append({
                        "comment_id": answer_record.comment_id, 
                        "status": "error", 
                        "error": str(e)
                    })
                    logger.error(f"Failed to process reply for comment {answer_record.comment_id}: {e}")

            return {
                "status": "success", 
                "processed_count": processed_count, 
                "total_found": len(pending_answers), 
                "results": results
            }

        except Exception as e:
            logger.error(f"Error in process_pending_replies: {e}")
            await session.rollback()
            return {"status": "error", "reason": str(e)}
        finally:
            await engine.dispose()
