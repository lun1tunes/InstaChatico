"""
Document Context Service

Retrieves and formats document content for AI agent context.
"""

import logging
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.client_document import ClientDocument

logger = logging.getLogger(__name__)


class DocumentContextService:
    """Service for retrieving document context for AI agents."""

    async def get_client_context(
        self,
        client_id: str,
        session: AsyncSession
    ) -> str:
        """
        Get formatted markdown context from all client documents.

        Args:
            client_id: Instagram business account ID
            session: Database session

        Returns:
            Formatted markdown string with all document content
        """
        try:
            # Fetch all completed documents for client
            stmt = select(ClientDocument).where(
                ClientDocument.client_id == client_id,
                ClientDocument.processing_status == "completed",
                ClientDocument.markdown_content.isnot(None)
            ).order_by(ClientDocument.created_at.desc())

            result = await session.execute(stmt)
            documents = result.scalars().all()

            if not documents:
                logger.info(f"No documents found for client {client_id}")
                return ""

            # Format documents into context
            context_parts = ["# Business Information\n"]

            for doc in documents:
                context_parts.append(f"\n## {doc.document_name}\n")
                if doc.description:
                    context_parts.append(f"*{doc.description}*\n")
                context_parts.append(f"\n{doc.markdown_content}\n")
                context_parts.append("\n---\n")

            context = "\n".join(context_parts)
            logger.info(f"Retrieved context for client {client_id}: {len(context)} characters from {len(documents)} documents")

            return context

        except Exception as e:
            logger.error(f"Error retrieving document context: {e}", exc_info=True)
            return ""

    async def get_document_summary(
        self,
        client_id: str,
        session: AsyncSession
    ) -> dict:
        """
        Get summary statistics about client documents.

        Args:
            client_id: Instagram business account ID
            session: Database session

        Returns:
            Dict with document statistics
        """
        try:
            stmt = select(ClientDocument).where(
                ClientDocument.client_id == client_id
            )

            result = await session.execute(stmt)
            documents = result.scalars().all()

            total = len(documents)
            completed = sum(1 for d in documents if d.processing_status == "completed")
            failed = sum(1 for d in documents if d.processing_status == "failed")
            pending = sum(1 for d in documents if d.processing_status == "pending")

            return {
                "total_documents": total,
                "completed": completed,
                "failed": failed,
                "pending": pending,
                "types": list(set(d.document_type for d in documents))
            }

        except Exception as e:
            logger.error(f"Error getting document summary: {e}")
            return {"error": str(e)}

    async def format_context_for_agent(
        self,
        client_id: str,
        session: AsyncSession
    ) -> str:
        """
        Format document context for AI agent (alias for get_client_context).

        Args:
            client_id: Instagram business account ID
            session: Database session

        Returns:
            Formatted markdown context for agent
        """
        return await self.get_client_context(client_id, session)


# Singleton instance
document_context_service = DocumentContextService()
