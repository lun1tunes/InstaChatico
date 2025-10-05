# Schema Architecture - Best Practices & Recommendations

## Current Structure Analysis

### ✅ What You Have Now

```
src/
├── core/
│   └── schemas/          # Domain/Business logic schemas
│       ├── classification.py
│       ├── answer.py
│       ├── comment.py
│       └── webhook.py
│
└── api_v1/
    └── comment_webhooks/
        └── schemas.py    # API-specific input validation schemas
```

## Architecture Question: Core Schemas in API Layer?

### ✅ **YES - This is GOOD practice!**

Here's why your current approach is correct:

### 1. **Separation of Concerns (Proper Layering)**

```
┌─────────────────────────────────────┐
│     API Layer (FastAPI Routes)      │
│  - Input validation (webhooks)      │
│  - HTTP-specific concerns           │
│  - Uses: core schemas for response  │
└─────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────┐
│      Core/Domain Layer              │
│  - Business logic schemas           │
│  - Database model validation        │
│  - Shared across all APIs           │
└─────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────┐
│      Database Layer (SQLAlchemy)    │
│  - ORM models                       │
│  - Uses: Pydantic for validation    │
└─────────────────────────────────────┘
```

**Why this works:**
- ✅ Core schemas = **domain/business logic** (classification, answers, comments)
- ✅ API schemas = **HTTP-specific validation** (webhook payloads, request bodies)
- ✅ API layer **imports and uses** core schemas for responses
- ✅ Avoids duplication between different API versions

### 2. **Real-World Example (Your Code)**

**Core Schema (Domain):**
```python
# core/schemas/comment.py
class CommentFullResponse(BaseModel):
    """Business logic: Complete comment representation"""
    id: str
    text: str
    classification: str | None
    answer: str | None
    # This represents your DOMAIN MODEL
```

**API Schema (HTTP-specific):**
```python
# api_v1/comment_webhooks/schemas.py
class WebhookPayload(BaseModel):
    """HTTP-specific: Instagram's webhook format"""
    entry: list[WebhookEntry]
    object: Literal["instagram"]
    # This is INSTAGRAM'S format, not your domain
```

**API Endpoint (Correct Usage):**
```python
# api_v1/comments/views.py
from core.schemas.comment import CommentFullResponse  # ✅ GOOD

@router.get("/{comment_id}/full", response_model=CommentFullResponse)
async def get_comment_full(...):
    # Returns domain model, not HTTP-specific schema
```

---

## Webhook Schemas - Should They Be Refactored?

### 🎯 **Recommendation: Keep Them Separate (Current Structure is Correct)**

### Why Webhook Schemas Should Stay in API Layer:

#### 1. **They're Instagram API-Specific (Not Domain Models)**

```python
# api_v1/comment_webhooks/schemas.py

class CommentValue(BaseModel):
    """This is INSTAGRAM's format"""
    from_: CommentAuthor = Field(..., alias="from")  # Instagram's weird "from" field
    media: CommentMedia
    text: str
```

**This is NOT your domain model!**
- It's Instagram's external API format
- It has Instagram-specific quirks (alias="from")
- It should NOT be in core (domain) layer

#### 2. **Different Purposes**

| Schema Type | Location | Purpose | Example |
|------------|----------|---------|---------|
| **Webhook Input** | `api_v1/comment_webhooks/schemas.py` | Validate Instagram's webhook payload | `WebhookPayload`, `CommentValue` |
| **Domain/Response** | `core/schemas/comment.py` | Your business logic representation | `CommentFullResponse` |
| **Database** | `core/models/instagram_comment.py` | Data persistence | `InstagramComment` |

#### 3. **Proper Flow (Your Current Architecture is Correct!)**

```python
# 1. Receive webhook (API-specific schema)
@router.post("/webhook")
async def process_webhook(
    webhook_data: WebhookPayload,  # Instagram's format
    ...
):
    # 2. Extract and transform to domain model
    comments = webhook_data.get_all_comments()

    for entry, comment_value in comments:  # comment_value is Instagram format
        # 3. Create YOUR domain model (database)
        instagram_comment = InstagramComment(
            id=comment_value.id,
            text=comment_value.text,
            username=comment_value.from_.username,  # Transform from Instagram format
            ...
        )

        # 4. Process with domain schemas
        classification = await classify(comment_value.text)

        # 5. Return domain response (NOT webhook schema)
        return CommentFullResponse.model_validate(instagram_comment)
```

---

## Recommended Schema Organization

### ✅ **Current Structure (Keep It!)**

```python
# ============================================
# CORE SCHEMAS (Domain/Business Logic)
# Location: core/schemas/
# Used by: All API versions, services, tasks
# ============================================

# core/schemas/comment.py
class CommentBase(BaseModel):
    """Domain model base"""

class CommentFullResponse(CommentBase):
    """Business logic response"""

# core/schemas/classification.py
class ClassificationResponse(BaseModel):
    """Classification domain model"""

# ============================================
# API-SPECIFIC SCHEMAS (HTTP/External)
# Location: api_v1/{endpoint}/schemas.py
# Used by: Specific API endpoints only
# ============================================

# api_v1/comment_webhooks/schemas.py
class WebhookPayload(BaseModel):
    """Instagram webhook format (external)"""

class CommentValue(BaseModel):
    """Instagram's comment representation"""
    from_: CommentAuthor = Field(alias="from")  # Instagram-specific

# api_v1/documents/schemas.py
class DocumentUploadRequest(BaseModel):
    """API-specific upload request"""
```

### ❌ **What NOT to Do**

```python
# DON'T put Instagram-specific schemas in core
# core/schemas/instagram_webhook.py  ❌ NO!

# DON'T duplicate domain models in API
# api_v1/comments/schemas.py
class CommentResponse(BaseModel):  # ❌ Duplicates core schema!
    id: str
    text: str
    # This should be in core/schemas/comment.py
```

---

## When to Create API-Specific Schemas vs Use Core

### Use **API-Specific Schemas** When:

1. **External API Format** (like Instagram webhooks)
   - `WebhookPayload` - Instagram's format
   - `CommentValue` - Instagram's comment structure

2. **HTTP-Specific Validation**
   - `WebhookVerification` - URL query params for webhook verification
   - Request bodies with specific HTTP constraints

3. **API Version-Specific**
   - If you add `api_v2/` later with different formats

### Use **Core Schemas** When:

1. **Domain/Business Logic**
   - `CommentFullResponse` - Your internal comment representation
   - `ClassificationResponse` - Your classification model

2. **Shared Across APIs**
   - If both `api_v1` and `api_v2` return same domain models

3. **Database Model Validation**
   - Pydantic models for SQLAlchemy ORM validation

---

## Refactoring Recommendations

### ✅ **Keep Current Structure (No Refactoring Needed!)**

Your webhook schemas are **correctly placed** in `api_v1/comment_webhooks/schemas.py` because:

1. They're Instagram API-specific (not domain models)
2. They have external API quirks (alias="from")
3. They're only used by webhook endpoints
4. They transform TO your domain models (not replace them)

### 🔄 **Only Refactor If:**

You find yourself **duplicating** webhook schemas across multiple API endpoints:

```python
# If you have this situation:
api_v1/comment_webhooks/schemas.py  # Has WebhookPayload
api_v1/media_webhooks/schemas.py    # ALSO has WebhookPayload ❌

# Then move to shared location:
core/schemas/instagram_webhooks.py  # Shared Instagram schemas ✅
```

But currently, your webhook schemas are **endpoint-specific**, so they're correctly placed!

---

## Best Practices Summary

### ✅ **DO:**

1. **Use core schemas for responses** in API endpoints
   ```python
   from core.schemas.comment import CommentFullResponse

   @router.get("/{id}/full", response_model=CommentFullResponse)
   ```

2. **Keep API-specific input schemas in API layer**
   ```python
   # api_v1/comment_webhooks/schemas.py
   class WebhookPayload(BaseModel):  # Instagram-specific, stays here
   ```

3. **Transform external → domain in endpoints**
   ```python
   webhook_data: WebhookPayload  # Input (Instagram format)
   →  # Transform
   return CommentFullResponse(...)  # Output (domain format)
   ```

### ❌ **DON'T:**

1. **Don't put external API schemas in core**
   ```python
   # core/schemas/instagram_webhook.py  ❌ NO!
   # These are Instagram-specific, not domain
   ```

2. **Don't duplicate domain models in API**
   ```python
   # api_v1/comments/schemas.py
   class CommentResponse(...):  # ❌ Use core schema instead!
   ```

3. **Don't mix concerns**
   ```python
   class CommentResponse(BaseModel):
       from_: str = Field(alias="from")  # ❌ Instagram quirk in domain model
   ```

---

## Your Current Architecture: ✅ EXCELLENT

```
✅ Core schemas = Domain models (classification, answers, comments)
✅ Webhook schemas = Instagram API-specific (stay in api_v1/comment_webhooks/)
✅ API endpoints = Use core schemas for responses
✅ Clear separation of concerns
✅ No duplication
✅ Follows DRY principle
✅ Scalable for api_v2, api_v3, etc.
```

**Conclusion: No refactoring needed! Your schema organization is already following best practices.** 🎯
