"""
Document Processing Celery Tasks

Async tasks for processing uploaded documents.
"""

import logging
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.celery_app import celery_app
from core.models.db_helper import db_helper
from core.models.client_document import ClientDocument
from core.services.s3_service import s3_service
from core.services.document_processing_service import document_processing_service

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, queue="llm_queue")
def process_document_task(self, document_id: str):
    """
    Process document: Download from S3, extract content, save markdown.

    Args:
        document_id: UUID of the document to process
    """
    import asyncio

    async def _process():
        async with db_helper.session_factory() as session:
            try:
                # Fetch document
                stmt = select(ClientDocument).where(ClientDocument.id == document_id)
                result = await session.execute(stmt)
                document = result.scalar_one_or_none()

                if not document:
                    logger.error(f"Document {document_id} not found")
                    return

                # Update status to processing
                document.processing_status = "processing"
                await session.commit()

                logger.info(f"Processing document: {document.document_name}")

                # Download from S3
                success, file_content, error = s3_service.download_file(document.s3_key)

                if not success:
                    raise Exception(f"Failed to download from S3: {error}")

                # Process document with pdfplumber/python-docx
                success, markdown, content_hash, error = document_processing_service.process_document(
                    file_content=file_content, filename=document.document_name, document_type=document.document_type
                )

                if not success:
                    raise Exception(f"Failed to process document: {error}")

                # Update document with results
                document.markdown_content = markdown
                document.content_hash = content_hash
                document.processing_status = "completed"
                document.processed_at = datetime.utcnow()
                document.processing_error = None

                await session.commit()

                logger.info(f"Successfully processed document {document_id}: {len(markdown)} chars of markdown")

            except Exception as e:
                logger.error(f"Error processing document {document_id}: {e}", exc_info=True)

                # Rollback current session first
                await session.rollback()

                # Update document with error using a fresh session
                try:
                    async with db_helper.session_factory() as error_session:
                        stmt = select(ClientDocument).where(ClientDocument.id == document_id)
                        result = await error_session.execute(stmt)
                        document = result.scalar_one_or_none()

                        if document:
                            document.processing_status = "failed"
                            document.processing_error = str(e)
                            await error_session.commit()
                except Exception as commit_error:
                    logger.error(f"Failed to update error status: {commit_error}")

                # Retry task
                raise self.retry(exc=e, countdown=60)

    # Run async function with a fresh event loop
    # This ensures no conflicts with existing event loops
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_process())
    finally:
        loop.close()


@celery_app.task
def reprocess_failed_documents():
    """
    Periodic task to reprocess failed documents.
    Can be scheduled with Celery Beat.
    """
    import asyncio

    async def _reprocess():
        async with db_helper.session_factory() as session:
            try:
                # Find failed documents
                stmt = select(ClientDocument).where(ClientDocument.processing_status == "failed").limit(10)

                result = await session.execute(stmt)
                failed_docs = result.scalars().all()

                logger.info(f"Found {len(failed_docs)} failed documents to reprocess")

                for doc in failed_docs:
                    # Queue for reprocessing
                    process_document_task.delay(str(doc.id))

            except Exception as e:
                logger.error(f"Error in reprocess task: {e}")

    asyncio.run(_reprocess())
