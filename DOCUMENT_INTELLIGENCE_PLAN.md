# Document Intelligence System - Implementation Plan

## 🎯 Goal
Add business context from client documents (PDFs, Excel, CSV, Word) to enhance AI reply quality for Instagram comments.

## 🏗️ Architecture Overview

```
┌─────────────────┐
│   S3 Storage    │ ← Store original documents
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│ Docling Service │ ← Extract & convert to Markdown
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│  PostgreSQL DB  │ ← Store metadata + markdown context
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│  Reply Agent    │ ← Use context in responses
└─────────────────┘
```

## 📊 Database Schema Design

### New Table: `client_documents`

```sql
CREATE TABLE client_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Client identification
    client_id VARCHAR(100) NOT NULL,  -- Instagram business account ID
    client_name VARCHAR(200),          -- Business name

    -- Document metadata
    document_name VARCHAR(500) NOT NULL,
    document_type VARCHAR(50) NOT NULL,  -- 'pdf', 'excel', 'csv', 'word', 'txt'
    description TEXT,                    -- Human-readable description

    -- S3 storage
    s3_bucket VARCHAR(200) NOT NULL,
    s3_key VARCHAR(500) NOT NULL,        -- S3 object key
    s3_url TEXT NOT NULL,                -- Full S3 URL (presigned or public)
    file_size_bytes BIGINT,              -- Original file size

    -- Processed content
    markdown_content TEXT,               -- Extracted content in markdown format
    content_hash VARCHAR(64),            -- SHA-256 hash for deduplication

    -- Processing status
    processing_status VARCHAR(50) DEFAULT 'pending',  -- pending, processing, completed, failed
    processing_error TEXT,               -- Error message if failed
    processed_at TIMESTAMP,              -- When processing completed

    -- AI/Search metadata
    embedding_status VARCHAR(50) DEFAULT 'pending',  -- For future vector search
    tags JSONB,                          -- Categorization tags

    -- Audit fields
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by VARCHAR(100),             -- User/system who uploaded

    -- Indexes
    INDEX idx_client_documents_client_id (client_id),
    INDEX idx_client_documents_status (processing_status),
    INDEX idx_client_documents_type (document_type),
    INDEX idx_client_documents_hash (content_hash),

    -- Constraints
    UNIQUE (client_id, content_hash),    -- Prevent duplicate documents
    CHECK (processing_status IN ('pending', 'processing', 'completed', 'failed')),
    CHECK (document_type IN ('pdf', 'excel', 'csv', 'word', 'txt', 'other'))
);
```

## 🔧 Technology Stack

### 1. **Docling** - Document Processing
- Best choice for PDF extraction
- Supports multiple formats
- Outputs clean markdown
- Handles tables, images, structure

```python
from docling.document_converter import DocumentConverter

converter = DocumentConverter()
result = converter.convert("document.pdf")
markdown = result.document.export_to_markdown()
```

### 2. **AWS S3 (boto3)** - Document Storage
```python
import boto3
s3_client = boto3.client('s3')
```

### 3. **Celery** - Async Processing
```python
@celery_app.task
def process_document_task(document_id: str):
    # Download from S3 → Process with Docling → Save markdown
    pass
```

## 📁 File Structure

```
src/core/
├── models/
│   └── client_document.py          # SQLAlchemy model
├── services/
│   ├── s3_service.py                # S3 upload/download
│   ├── document_processing_service.py  # Docling integration
│   └── document_context_service.py  # Context retrieval for agent
├── tasks/
│   └── document_tasks.py            # Celery tasks
└── schemas/
    └── document_schemas.py          # Pydantic models

src/api_v1/
└── documents/
    ├── views.py                     # REST endpoints
    └── schemas.py                   # Request/response models
```

## 🔄 Processing Flow

### 1. Upload Flow
```
User uploads document
    ↓
API receives file
    ↓
Upload to S3
    ↓
Create DB record (status: pending)
    ↓
Queue Celery task
    ↓
Return document_id to user
```

### 2. Processing Flow (Celery Task)
```
Download from S3
    ↓
Detect document type
    ↓
Process with Docling
    ↓
Convert to Markdown
    ↓
Calculate content hash
    ↓
Update DB record (markdown_content, status: completed)
    ↓
Optional: Generate embeddings for vector search
```

### 3. Query Flow (Reply Agent)
```
Receive Instagram comment
    ↓
Identify client_id from media owner
    ↓
Fetch client documents (markdown_content)
    ↓
Include in agent context
    ↓
Generate informed response
```

## 🎨 Implementation Steps

### Phase 1: Core Infrastructure ✅
1. ✅ Create database model
2. ✅ Create migration
3. ✅ Add S3 service
4. ✅ Add Docling processing service

### Phase 2: API & Processing ✅
5. ✅ Create API endpoints (upload, list, get, delete)
6. ✅ Implement Celery task for processing
7. ✅ Add document context service

### Phase 3: Agent Integration ✅
8. ✅ Modify reply agent to fetch document context
9. ✅ Add context to agent prompts
10. ✅ Test end-to-end flow

### Phase 4: Testing & Polish ✅
11. ✅ Unit tests
12. ✅ Integration tests
13. ✅ Documentation

## 📝 Example Usage

### Upload Document
```bash
curl -X POST http://localhost:4291/api/v1/documents/upload \
  -F "file=@business_catalog.pdf" \
  -F "client_id=instagram_account_123" \
  -F "client_name=Real Estate Agency" \
  -F "description=Product catalog with prices"
```

### Response
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "document_name": "business_catalog.pdf",
  "processing_status": "pending",
  "s3_url": "https://s3.amazonaws.com/bucket/docs/...",
  "created_at": "2025-10-03T20:00:00Z"
}
```

### Query Documents
```bash
curl http://localhost:4291/api/v1/documents?client_id=instagram_account_123
```

### Get Document
```bash
curl http://localhost:4291/api/v1/documents/550e8400-e29b-41d4-a716-446655440000
```

## 🔌 Agent Integration

### Before (no context):
```python
agent_input = f"Comment: {comment_text}\nMedia: {media_caption}"
```

### After (with context):
```python
# Fetch client documents
docs = await document_context_service.get_client_context(client_id)

agent_input = f"""
Client Business Context:
{docs}

---
Media: {media_caption}
Comment from @{username}: {comment_text}

Please provide a helpful, context-aware response.
"""
```

## 📦 Dependencies to Add

```toml
[tool.poetry.dependencies]
# Document processing
docling = "^2.0.0"             # PDF/document to markdown
python-magic = "^0.4.27"       # File type detection

# AWS S3
boto3 = "^1.34.0"              # AWS SDK
botocore = "^1.34.0"

# Optional: Vector search (future)
# pgvector = "^0.3.0"          # PostgreSQL vector extension
```

## 🎯 Benefits

✅ **Better responses** - AI has business context
✅ **Scalable** - S3 + async processing
✅ **Production-ready** - Error handling, retries
✅ **Flexible** - Supports multiple document types
✅ **Efficient** - Markdown format optimized for LLMs
✅ **Deduplication** - Content hash prevents duplicates
✅ **Searchable** - Can add vector search later

## 🚀 Future Enhancements

1. **Vector Search** - Use pgvector for semantic document search
2. **Chunking** - Split large documents for better retrieval
3. **Multi-language** - OCR for scanned documents
4. **Excel Processing** - Extract structured data from spreadsheets
5. **Auto-tagging** - AI-powered document categorization
6. **Webhooks** - Notify when processing completes
7. **Versioning** - Track document updates

## 🔒 Security Considerations

- ✅ Presigned S3 URLs (expiring links)
- ✅ Client ID isolation (can't access other clients' docs)
- ✅ File type validation
- ✅ Size limits (prevent abuse)
- ✅ Virus scanning (optional with ClamAV)
- ✅ Access logs

## 📊 Monitoring

- Processing success/failure rates
- Average processing time
- S3 storage usage
- Document count per client
- Agent context usage

## Ready to implement?

Let me know if you want me to start implementing this system! I'll create:
1. Database model
2. Migration
3. S3 service
4. Docling processing service
5. API endpoints
6. Celery tasks
7. Agent integration
8. Tests

This will be a production-ready document intelligence system! 🚀
