"""
Database operations for webhook processing.
Handles all database interactions for comments and classifications.
"""

from datetime import datetime
from typing import Dict, Any, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select

from core.models.instagram_comment import InstagramComment
from core.models.comment_classification import CommentClassification, ProcessingStatus
from core.models.question_answer import QuestionAnswer
from core.exceptions import DatabaseError, DuplicateRecordError
from core.logging_config import get_logger

logger = get_logger(__name__, "webhook_crud")


class WebhookCRUD:
    """Database operations for webhook processing"""
    
    async def create_comment(
        self,
        session: AsyncSession,
        comment_data: Dict[str, Any]
    ) -> InstagramComment:
        """
        Create a new Instagram comment record
        
        Args:
            session: Database session
            comment_data: Comment data dictionary
            
        Returns:
            Created InstagramComment instance
            
        Raises:
            DuplicateRecordError: If comment already exists
            DatabaseError: For other database errors
        """
        try:
            comment = InstagramComment(**comment_data)
            session.add(comment)
            await session.commit()
            await session.refresh(comment)
            
            logger.info(
                "Created Instagram comment",
                extra_fields={"comment_id": comment.id},
                operation="create_comment"
            )
            
            return comment
            
        except IntegrityError as e:
            await session.rollback()
            logger.warning(
                f"Comment {comment_data.get('id')} already exists",
                extra_fields={"error": str(e)},
                operation="create_comment"
            )
            raise DuplicateRecordError(f"Comment already exists: {comment_data.get('id')}")
        except Exception as e:
            await session.rollback()
            logger.error(
                "Failed to create comment",
                extra_fields={"error": str(e), "comment_id": comment_data.get('id')},
                operation="create_comment"
            )
            raise DatabaseError(f"Failed to create comment: {str(e)}")
    
    async def get_comment(
        self,
        session: AsyncSession,
        comment_id: str
    ) -> Optional[InstagramComment]:
        """
        Get Instagram comment by ID
        
        Args:
            session: Database session
            comment_id: Comment ID
            
        Returns:
            InstagramComment instance or None if not found
        """
        try:
            result = await session.execute(
                select(InstagramComment).where(InstagramComment.id == comment_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(
                "Failed to get comment",
                extra_fields={"error": str(e), "comment_id": comment_id},
                operation="get_comment"
            )
            raise DatabaseError(f"Failed to get comment: {str(e)}")
    
    async def create_classification(
        self,
        session: AsyncSession,
        comment_id: str,
        status: ProcessingStatus = ProcessingStatus.PENDING
    ) -> CommentClassification:
        """
        Create a new classification record for a comment
        
        Args:
            session: Database session
            comment_id: Comment ID
            status: Initial processing status
            
        Returns:
            Created CommentClassification instance
        """
        try:
            classification = CommentClassification(
                comment_id=comment_id,
                processing_status=status
            )
            session.add(classification)
            await session.commit()
            await session.refresh(classification)
            
            logger.info(
                "Created classification record",
                extra_fields={"comment_id": comment_id, "status": status.value},
                operation="create_classification"
            )
            
            return classification
            
        except IntegrityError as e:
            await session.rollback()
            logger.warning(
                f"Classification for comment {comment_id} already exists",
                extra_fields={"error": str(e)},
                operation="create_classification"
            )
            raise DuplicateRecordError(f"Classification already exists for comment: {comment_id}")
        except Exception as e:
            await session.rollback()
            logger.error(
                "Failed to create classification",
                extra_fields={"error": str(e), "comment_id": comment_id},
                operation="create_classification"
            )
            raise DatabaseError(f"Failed to create classification: {str(e)}")
    
    async def update_classification(
        self,
        session: AsyncSession,
        comment_id: str,
        classification_data: Dict[str, Any]
    ) -> Optional[CommentClassification]:
        """
        Update classification record with AI results
        
        Args:
            session: Database session
            comment_id: Comment ID
            classification_data: Classification data to update
            
        Returns:
            Updated CommentClassification instance or None if not found
        """
        try:
            result = await session.execute(
                select(CommentClassification).where(
                    CommentClassification.comment_id == comment_id
                )
            )
            classification = result.scalar_one_or_none()
            
            if not classification:
                logger.warning(
                    f"Classification not found for comment {comment_id}",
                    operation="update_classification"
                )
                return None
            
            # Update fields
            for field, value in classification_data.items():
                if hasattr(classification, field):
                    setattr(classification, field, value)
            
            await session.commit()
            await session.refresh(classification)
            
            logger.info(
                "Updated classification",
                extra_fields={
                    "comment_id": comment_id,
                    "classification": classification_data.get("classification"),
                    "confidence": classification_data.get("confidence")
                },
                operation="update_classification"
            )
            
            return classification
            
        except Exception as e:
            await session.rollback()
            logger.error(
                "Failed to update classification",
                extra_fields={"error": str(e), "comment_id": comment_id},
                operation="update_classification"
            )
            raise DatabaseError(f"Failed to update classification: {str(e)}")
    
    async def check_if_reply(
        self,
        session: AsyncSession,
        comment_id: str
    ) -> bool:
        """
        Check if a comment ID exists as a reply in our system
        (to prevent infinite loops)
        
        Args:
            session: Database session
            comment_id: Comment ID to check
            
        Returns:
            True if this comment ID is a reply we sent
        """
        try:
            result = await session.execute(
                select(QuestionAnswer).where(QuestionAnswer.reply_id == comment_id)
            )
            reply_record = result.scalar_one_or_none()
            
            if reply_record:
                logger.info(
                    f"Comment {comment_id} is our own reply, skipping",
                    operation="check_if_reply"
                )
                return True
            
            return False
            
        except Exception as e:
            logger.error(
                "Failed to check if comment is reply",
                extra_fields={"error": str(e), "comment_id": comment_id},
                operation="check_if_reply"
            )
            # On error, assume it's not a reply to be safe
            return False
    
    async def get_processing_stats(
        self,
        session: AsyncSession,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Get processing statistics for monitoring
        
        Args:
            session: Database session
            limit: Limit for recent records
            
        Returns:
            Dictionary with processing statistics
        """
        try:
            # Get recent comments count
            comments_result = await session.execute(
                select(InstagramComment).limit(limit)
            )
            recent_comments = len(comments_result.scalars().all())
            
            # Get classification status counts
            classifications_result = await session.execute(
                select(CommentClassification.processing_status).limit(limit)
            )
            statuses = classifications_result.scalars().all()
            
            status_counts = {}
            for status in ProcessingStatus:
                status_counts[status.value] = sum(1 for s in statuses if s == status)
            
            return {
                "recent_comments": recent_comments,
                "classification_status": status_counts,
                "total_processed": len(statuses)
            }
            
        except Exception as e:
            logger.error(
                "Failed to get processing stats",
                extra_fields={"error": str(e)},
                operation="get_processing_stats"
            )
            return {"error": str(e)}


# Global instance
webhook_crud = WebhookCRUD()
