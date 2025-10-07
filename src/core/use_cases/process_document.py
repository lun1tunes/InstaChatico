"""Process document use case - handles document processing business logic."""

from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories.document import DocumentRepository
from ..services.s3_service import s3_service
from ..services.document_processing_service import document_processing_service
from ..utils.decorators import handle_task_errors
from ..utils.time import now_db_utc


class ProcessDocumentUseCase:
    """Use case for processing uploaded documents."""

    def __init__(
        self,
        session: AsyncSession,
        s3_service_instance=None,
        doc_processing_service=None
    ):
        self.session = session
        self.document_repo = DocumentRepository(session)
        self.s3_service = s3_service_instance or s3_service
        self.doc_processing = doc_processing_service or document_processing_service

    @handle_task_errors()
    async def execute(self, document_id: str) -> Dict[str, Any]:
        """Execute document processing use case."""
        # 1. Get document using repository
        document = await self.document_repo.get_by_id(document_id)

        if not document:
            return {"status": "error", "reason": f"Document {document_id} not found"}

        # 2. Update status to processing using repository method
        await self.document_repo.mark_processing(document)
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

            # 5. Update document with results using repository method
            await self.document_repo.mark_completed(document, markdown)
            document.content_hash = content_hash
            await self.session.commit()

            return {
                "status": "success",
                "document_id": document_id,
                "markdown_length": len(markdown),
            }

        except Exception as exc:
            # Update document with error using repository method
            await self.document_repo.mark_failed(document, str(exc))
            await self.session.commit()
            raise exc
