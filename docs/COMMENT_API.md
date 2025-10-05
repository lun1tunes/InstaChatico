# Comment Management API Documentation

## Overview

Comprehensive REST API for managing Instagram comments with DRY-compliant Pydantic schemas.

## Architecture

### Pydantic Schema Structure (DRY Principle)

All schemas are built using composition from base components:

**Base Schemas** (`core/schemas/comment.py`):
- `CommentBase` - Core comment fields (id, text, username, etc.)
- `HidingInfoBase` - Hiding status fields
- `ClassificationInfoBase` - Classification data fields
- `AnswerInfoBase` - Answer generation fields
- `ReplyInfoBase` - Reply status fields
- `TokenUsageBase` - Token usage tracking

**Response Schemas** (composed from bases):
- `CommentDetailResponse` - Basic comment + hiding info
- `CommentWithClassificationResponse` - Comment + classification
- `CommentWithAnswerResponse` - Comment + answer
- `CommentFullResponse` - Complete data (all fields)

---

## Endpoints

### 1. Get Comment (Basic Info)

**GET** `/api/v1/comments/{comment_id}`

Returns basic comment information with hiding status.

**Response:** `CommentDetailResponse`

```bash
curl "http://localhost:4291/api/v1/comments/18073146182180610"
```

**Response Example:**
```json
{
  "id": "18073146182180610",
  "text": "Подскажите в этот ваш кокосик насрали?",
  "username": "lunitunestmb",
  "user_id": "778695431740726",
  "media_id": "18090018553877686",
  "created_at": "2025-10-05T13:52:52",
  "is_hidden": true,
  "hidden_at": "2025-10-05T14:07:37.187298",
  "parent_id": null,
  "conversation_id": "first_question_comment_18073146182180610"
}
```

---

### 2. Get Comment with Classification

**GET** `/api/v1/comments/{comment_id}/classification`

Returns comment with classification details (category, confidence, reasoning, tokens).

**Response:** `CommentWithClassificationResponse`

```bash
curl "http://localhost:4291/api/v1/comments/18073146182180610/classification"
```

**Response Example:**
```json
{
  "id": "18073146182180610",
  "text": "Подскажите в этот ваш кокосик насрали?",
  "username": "lunitunestmb",
  "classification": "urgent issue / complaint",
  "confidence": 78,
  "reasoning": "Комментарий выражает обеспокоенность...",
  "input_tokens": 5036,
  "output_tokens": 3300,
  "processing_status": "COMPLETED",
  "processing_started_at": "2025-10-05T13:53:03.482825",
  "processing_completed_at": "2025-10-05T13:53:20.361575"
}
```

---

### 3. Get Comment with Answer

**GET** `/api/v1/comments/{comment_id}/answer`

Returns comment with answer generation details.

**Response:** `CommentWithAnswerResponse`

```bash
curl "http://localhost:4291/api/v1/comments/{comment_id}/answer"
```

**Response Fields:**
- All `CommentDetailResponse` fields
- `answer` - Generated answer text
- `answer_confidence` - Answer confidence (0.0-1.0)
- `answer_quality_score` - Quality score (0-100)
- `input_tokens` / `output_tokens` - Token usage
- `processing_status` / timestamps

---

### 4. Get Comment (Full Info)

**GET** `/api/v1/comments/{comment_id}/full`

Returns complete comment information with all related data.

**Response:** `CommentFullResponse`

```bash
curl "http://localhost:4291/api/v1/comments/18073146182180610/full"
```

**Response Example:**
```json
{
  "id": "18073146182180610",
  "text": "...",
  "classification": "urgent issue / complaint",
  "confidence": 78,
  "reasoning": "...",
  "classification_status": "COMPLETED",
  "classification_input_tokens": 5036,
  "classification_output_tokens": 3300,
  "answer": null,
  "answer_status": null,
  "reply_sent": false,
  "reply_status": null
}
```

---

### 5. List Comments (with Pagination & Filters)

**GET** `/api/v1/comments/`

List comments with pagination and filtering options.

**Query Parameters:**
- `page` (int, default=1) - Page number
- `page_size` (int, default=20, max=100) - Items per page
- `classification` (string, optional) - Filter by classification
- `is_hidden` (bool, optional) - Filter by hidden status
- `has_reply` (bool, optional) - Filter by reply status

**Response:** `CommentListResponse`

```bash
# Get first page
curl "http://localhost:4291/api/v1/comments/?page=1&page_size=5"

# Filter by classification
curl "http://localhost:4291/api/v1/comments/?classification=question%20/%20inquiry"

# Filter hidden comments
curl "http://localhost:4291/api/v1/comments/?is_hidden=true"

# Filter comments with replies
curl "http://localhost:4291/api/v1/comments/?has_reply=true"
```

**Response Example:**
```json
{
  "comments": [
    {
      "id": "18073146182180610",
      "text": "...",
      "classification": "urgent issue / complaint",
      "confidence": 78,
      "is_hidden": true,
      "reply_sent": false
    }
  ],
  "total": 12,
  "page": 1,
  "page_size": 5,
  "total_pages": 3
}
```

---

### 6. Hide Comment

**POST** `/api/v1/comments/{comment_id}/hide`

Hide a comment on Instagram (queues Celery task).

**Response:** `HideCommentResponse`

```bash
curl -X POST "http://localhost:4291/api/v1/comments/18073146182180610/hide"
```

**Response (Queued):**
```json
{
  "status": "queued",
  "message": "Hide task queued for comment 18073146182180610",
  "comment_id": "18073146182180610",
  "task_id": "23ce43cc-7343-4ff0-88e3-3d563a95ab37"
}
```

**Response (Already Hidden):**
```json
{
  "status": "already_hidden",
  "message": "Comment 18073146182180610 is already hidden",
  "comment_id": "18073146182180610",
  "hidden_at": "2025-10-05T14:07:37.187298"
}
```

---

### 7. Unhide Comment

**POST** `/api/v1/comments/{comment_id}/unhide`

Unhide a comment on Instagram (executes immediately).

**Response:** `UnhideCommentResponse`

```bash
curl -X POST "http://localhost:4291/api/v1/comments/18073146182180610/unhide"
```

**Response (Success):**
```json
{
  "status": "success",
  "message": "Comment 18073146182180610 unhidden successfully",
  "comment_id": "18073146182180610"
}
```

**Response (Not Hidden):**
```json
{
  "status": "not_hidden",
  "message": "Comment 18073146182180610 is not hidden",
  "comment_id": "18073146182180610"
}
```

---

### 8. Send Manual Reply

**POST** `/api/v1/comments/{comment_id}/reply?message={text}`

Send a manual reply to a comment (queues Celery task).

**Query Parameters:**
- `message` (string, 1-500 chars) - Reply text

**Response:** `SendReplyResponse`

```bash
curl -X POST "http://localhost:4291/api/v1/comments/18078462377012735/reply?message=Thanks%20for%20your%20question!"
```

**Response:**
```json
{
  "status": "queued",
  "message": "Reply task queued for comment 18078462377012735",
  "comment_id": "18078462377012735",
  "task_id": "cbc35a53-2482-4ee1-8708-2d82a2765630",
  "reply_text": "Thanks for your question!"
}
```

---

## Error Responses

### 404 Not Found
```json
{
  "detail": "Comment {comment_id} not found"
}
```

### 500 Internal Server Error
```json
{
  "detail": "Failed to unhide comment: {error_details}"
}
```

---

## Schema Reusability (DRY)

All response schemas inherit from base components, ensuring:

✅ **No duplicate field definitions**
✅ **Consistent data structure**
✅ **Easy maintenance and updates**
✅ **Type safety with Pydantic validation**

Example composition:
```python
# Base components
class CommentBase(BaseModel):
    id: str
    text: str
    username: str
    ...

class ClassificationInfoBase(BaseModel):
    classification: str | None
    confidence: int | None
    ...

# Composed response
class CommentWithClassificationResponse(CommentBase, ClassificationInfoBase):
    # Automatically includes all fields from both bases
    processing_status: str | None
    ...
```

---

## Testing Examples

### Test Full Workflow

```bash
# 1. Get comment info
curl "http://localhost:4291/api/v1/comments/18073146182180610"

# 2. Get classification
curl "http://localhost:4291/api/v1/comments/18073146182180610/classification"

# 3. Hide comment
curl -X POST "http://localhost:4291/api/v1/comments/18073146182180610/hide"

# 4. Check status
curl "http://localhost:4291/api/v1/comments/18073146182180610"

# 5. Unhide comment
curl -X POST "http://localhost:4291/api/v1/comments/18073146182180610/unhide"

# 6. Send manual reply
curl -X POST "http://localhost:4291/api/v1/comments/18073146182180610/reply?message=Thank%20you!"

# 7. List all comments with filters
curl "http://localhost:4291/api/v1/comments/?page=1&page_size=10&classification=question%20/%20inquiry"
```
