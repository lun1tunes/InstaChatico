"""
Pydantic schemas for document API endpoints.
"""

from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
from uuid import UUID


class DocumentUploadResponse(BaseModel):
    """Response after uploading a document."""

    id: UUID
    document_name: str
    document_type: str
    s3_url: str
    processing_status: str
    created_at: datetime

    class Config:
        from_attributes = True


class DocumentResponse(BaseModel):
    """Full document information."""

    id: UUID
    client_id: str
    client_name: Optional[str] = None
    document_name: str
    document_type: str
    description: Optional[str] = None
    s3_url: str
    file_size_bytes: Optional[int] = None
    markdown_content: Optional[str] = None
    processing_status: str
    processing_error: Optional[str] = None
    processed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    """List of documents."""

    total: int
    documents: List[DocumentResponse]


class DocumentSummaryResponse(BaseModel):
    """Document statistics summary."""

    total_documents: int
    completed: int
    failed: int
    pending: int
    types: List[str]
