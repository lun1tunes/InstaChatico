"""Process document use case - handles document processing business logic."""

from typing import Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models.document import Document
from ..services.s3_service import s3_service
from ..services.document_processing_service import document_processing_service
from ..utils.decorators import handle_task_errors


class ProcessDocumentUseCase:
    """Use case for processing uploaded documents."""

    def __init__(
        self,
        session: AsyncSession,
        s3_service_instance=None,
        doc_processing_service=None
    ):
        self.session = session
        self.s3_service = s3_service_instance or s3_service
        self.doc_processing = doc_processing_service or document_processing_service

    @handle_task_errors()
    async def execute(self, document_id: str) -> Dict[str, Any]:
        """Execute document processing use case."""
        # 1. Get document
        stmt = select(Document).where(Document.id == document_id)
        result = await self.session.execute(stmt)
        document = result.scalar_one_or_none()

        if not document:
            return {"status": "error", "reason": f"Document {document_id} not found"}

        # 2. Update status to processing
        document.processing_status = "processing"
        await self.session.commit()

        try:
            # 3. Download from S3
            success, file_content, error = self.s3_service.download_file(document.s3_key)
            if not success:
                raise Exception(f"Failed to download from S3: {error}")

            # 4. Process document
            success, markdown, content_hash, error = self.doc_processing.process_document(
                file_content=file_content,
                filename=document.document_name,
                document_type=document.document_type
            )
            if not success:
                raise Exception(f"Failed to process document: {error}")

            # 5. Update document with results
            document.markdown_content = markdown
            document.content_hash = content_hash
            document.processing_status = "completed"
            document.processed_at = datetime.utcnow()
            document.processing_error = None

            await self.session.commit()

            return {
                "status": "success",
                "document_id": document_id,
                "markdown_length": len(markdown),
            }

        except Exception as exc:
            # Update document with error
            document.processing_status = "failed"
            document.processing_error = str(exc)
            await self.session.commit()
            raise exc
