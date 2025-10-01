# Development Mode Testing - Implementation Summary

## Overview

This document describes the implementation of the test endpoint for Instagram comment processing that works in **DEVELOPMENT_MODE**.

## What Was Implemented

### 1. Test Endpoint: `/api/v1/webhook/test`

**Location**: `src/api_v1/comment_webhooks/views.py`

**Purpose**: Process Instagram comments through the full pipeline without posting to Instagram.

**Features**:
- ✅ Only accessible when `DEVELOPMENT_MODE=true`
- ✅ Processes comments through classification → answer generation
- ✅ Creates all database records (comments, classifications, answers)
- ✅ Returns answer in HTTP response (instead of posting to Instagram)
- ✅ Skips actual Instagram API calls
- ✅ Synchronous processing for immediate feedback

### 2. Test Payload Schema

**Location**: `src/api_v1/comment_webhooks/schemas.py`

**Schema**: `TestCommentPayload`

```python
class TestCommentPayload(BaseModel):
    comment_id: str          # Any unique test ID
    media_id: str            # Test media ID
    user_id: str             # Test user ID
    username: str            # Test username
    text: str                # Comment text to process
    parent_id: str | None    # Optional: for testing replies
    media_caption: str | None  # Optional: provides context to AI
    media_url: str | None    # Optional: media URL
```

### 3. Development Mode Check in Instagram Reply Task

**Location**: `src/core/tasks/instagram_reply_tasks.py`

**Modification**: Added check for `DEVELOPMENT_MODE` before Instagram API call:

```python
if development_mode:
    # Skip actual Instagram API call
    reply_result = {
        "success": True,
        "reply_id": f"test_reply_{comment_id}",
        "response": {"test_mode": True}
    }
else:
    # Normal Instagram API call
    instagram_service = InstagramGraphAPIService()
    reply_result = await instagram_service.send_reply_to_comment(...)
```

**Result**: All database operations happen normally, but Instagram API is never called.

---

## How It Works

### Flow Diagram

```
POST /api/v1/webhook/test
         ↓
Check DEVELOPMENT_MODE=true?
         ↓
Create/Update Media Record
         ↓
Create/Update Comment Record
         ↓
Create Classification Record
         ↓
┌────────────────────────────┐
│  Run Classification        │
│  (sync, wait for result)   │
└────────────────────────────┘
         ↓
Is it a "question / inquiry"?
         ↓ YES
┌────────────────────────────┐
│  Generate Answer           │
│  (sync, wait for result)   │
│  - May use embedding_search│
│  - May use image analysis  │
└────────────────────────────┘
         ↓
Queue Instagram Reply Task
         ↓
Reply Task Checks DEVELOPMENT_MODE
         ↓
Skip Instagram API Call ✅
         ↓
Mark as "sent" in Database
         ↓
Return Response with Answer ✅
```

### What Gets Created in Database

**For every test comment**:
1. `media` record (if doesn't exist)
2. `instagram_comments` record
3. `comments_classification` record with:
   - classification type
   - confidence score
   - reasoning
   - sentiment/toxicity scores

**For questions only**:
4. `question_messages_answers` record with:
   - generated answer
   - confidence & quality scores
   - reply_sent = true
   - reply_status = "sent"
   - reply_id = "test_reply_{comment_id}"

---

## Configuration

### Enable Development Mode

Add to `.env`:
```bash
DEVELOPMENT_MODE=true
```

Restart services:
```bash
cd /var/www/instachatico/app/docker
docker-compose restart instachatico celery_worker
```

### Verify Configuration

```bash
# Check environment variable
docker exec instachatico env | grep DEVELOPMENT_MODE

# Should output:
# DEVELOPMENT_MODE=true
```

---

## Usage Examples

### Basic Usage (cURL)

```bash
curl -X POST http://localhost:4291/api/v1/webhook/test \
  -H "Content-Type: application/json" \
  -d '{
    "comment_id": "test_001",
    "media_id": "media_001",
    "user_id": "user_001",
    "username": "test_customer",
    "text": "Какие у вас есть квартиры?"
  }'
```

### Using Python

```python
import requests

payload = {
    "comment_id": "test_python_001",
    "media_id": "media_python_001",
    "user_id": "user_123",
    "username": "python_tester",
    "text": "Сколько стоит консультация?",
    "media_caption": "Профессиональные консультации"
}

response = requests.post(
    "http://localhost:4291/api/v1/webhook/test",
    json=payload
)

print(response.json())
```

### Response Structure

```json
{
  "status": "success",
  "comment_id": "test_001",
  "classification": "question / inquiry",
  "confidence": 92,
  "reasoning": "Customer is asking about available apartments",
  "answer": "У нас есть несколько вариантов квартир...",
  "answer_confidence": 0.88,
  "answer_quality_score": 85,
  "processing_details": {
    "classification_result": {
      "status": "success",
      "comment_id": "test_001",
      "classification": "question / inquiry",
      "confidence": 92
    },
    "answer_result": {
      "status": "success",
      "comment_id": "test_001",
      "answer": "...",
      "confidence": 0.88,
      "quality_score": 85
    }
  }
}
```

---

## Testing Different Scenarios

### 1. Question with Embedding Search

```json
{
  "comment_id": "test_embedding_001",
  "media_id": "media_001",
  "user_id": "user_001",
  "username": "buyer",
  "text": "Какие квартиры у вас есть в центре города?",
  "media_caption": "Новостройки в центре"
}
```

**Expected**: Agent uses `embedding_search` tool to find apartments.

### 2. Conversation Threading

First comment:
```json
{
  "comment_id": "conv_parent_001",
  "media_id": "media_002",
  "user_id": "user_002",
  "username": "interested_buyer",
  "text": "Расскажите о ваших услугах",
  "media_caption": "Консультации по недвижимости"
}
```

Reply:
```json
{
  "comment_id": "conv_reply_001",
  "media_id": "media_002",
  "user_id": "user_002",
  "username": "interested_buyer",
  "text": "А сколько это стоит?",
  "parent_id": "conv_parent_001",
  "media_caption": "Консультации по недвижимости"
}
```

**Expected**: Second answer uses context from first question.

### 3. Non-Question Classifications

Positive feedback:
```json
{
  "comment_id": "test_positive_001",
  "media_id": "media_003",
  "user_id": "user_003",
  "username": "happy_client",
  "text": "Отличный сервис, спасибо! 😊"
}
```

**Expected**: 
- Classification: "positive feedback"
- No answer generated
- `answer` field = null in response

Critical feedback:
```json
{
  "comment_id": "test_critical_001",
  "media_id": "media_003",
  "user_id": "user_004",
  "username": "disappointed",
  "text": "Качество не соответствует ожиданиям"
}
```

**Expected**:
- Classification: "critical feedback"
- Telegram notification triggered
- No answer generated

### 4. OOD (Out-of-Distribution) Detection

```json
{
  "comment_id": "test_ood_001",
  "media_id": "media_004",
  "user_id": "user_005",
  "username": "confused_user",
  "text": "Вы продаете пиццу?"
}
```

**Expected**:
- Classification: "question / inquiry"
- Answer: Politely says "We don't sell pizza" (OOD detected)

---

## Differences from Production Mode

| Feature | Production (`DEVELOPMENT_MODE=false`) | Development (`DEVELOPMENT_MODE=true`) |
|---------|--------------------------------------|--------------------------------------|
| **Test Endpoint** | ❌ Returns 403 | ✅ Accessible |
| **Instagram API Calls** | ✅ Actually posts replies | ❌ Skipped (simulated) |
| **Database Records** | ✅ Created | ✅ Created (identical) |
| **Answer in Response** | ❌ Not returned | ✅ Returned in HTTP response |
| **Celery Tasks** | ✅ Async queued | ✅ Async queued (but API skipped) |
| **Telegram Notifications** | ✅ Sent | ✅ Sent (if configured) |
| **Agent Processing** | ✅ Full pipeline | ✅ Full pipeline (identical) |
| **Processing Time** | Fast (async) | Slower (waits for result) |

---

## Validation & Testing

### Check Database Records

```sql
-- List all test comments
SELECT 
  ic.id,
  ic.text,
  cc.classification,
  cc.confidence,
  qa.answer,
  qa.reply_sent,
  qa.reply_status
FROM instagram_comments ic
LEFT JOIN comments_classification cc ON cc.comment_id = ic.id
LEFT JOIN question_messages_answers qa ON qa.comment_id = ic.id
WHERE ic.id LIKE 'test_%'
ORDER BY ic.created_at DESC;
```

### Verify Instagram API Skipped

```bash
# Watch logs
docker-compose logs -f instachatico celery_worker

# Look for this log message:
# "DEVELOPMENT_MODE: Skipping Instagram API call for comment test_XXX"
```

### Test Full Flow

```bash
# 1. Send test request
curl -X POST http://localhost:4291/api/v1/webhook/test \
  -H "Content-Type: application/json" \
  -d @test_payload.json

# 2. Check response has answer field
# 3. Check database has records
# 4. Verify no Instagram API call in logs
```

---

## Troubleshooting

### Error: "Test endpoint only accessible in DEVELOPMENT_MODE=true"

**Cause**: `DEVELOPMENT_MODE` not set or set to `false`

**Fix**:
```bash
# Add to .env
echo "DEVELOPMENT_MODE=true" >> /var/www/instachatico/app/.env

# Restart
docker-compose restart instachatico celery_worker
```

### Error: "Classification failed"

**Possible causes**:
1. OpenAI API key invalid or expired
2. Celery workers not running
3. Database connection issue
4. Redis not running

**Debug**:
```bash
# Check all services
docker-compose ps

# Check OpenAI key
docker exec instachatico env | grep OPENAI_API_KEY

# Test OpenAI directly
docker exec instachatico python -c "
from openai import OpenAI
client = OpenAI()
response = client.embeddings.create(model='text-embedding-3-small', input='test')
print('OK')
"
```

### Answer is null even for questions

**Possible causes**:
1. Classification didn't detect as "question / inquiry"
2. Answer generation failed
3. Check `processing_details` in response

**Check classification**:
```sql
SELECT classification, confidence, reasoning 
FROM comments_classification 
WHERE comment_id = 'your_test_id';
```

### Timeout errors

**Cause**: Processing takes too long (OpenAI API, embeddings, etc.)

**Solutions**:
1. Increase request timeout in Postman/client
2. Check OpenAI API status
3. Monitor processing time in logs

---

## Best Practices

### 1. Use Unique Test IDs

```python
import uuid
comment_id = f"test_{uuid.uuid4().hex[:8]}"
```

### 2. Clean Up Test Data Regularly

```sql
-- Delete all test records
DELETE FROM instagram_comments WHERE id LIKE 'test_%';
DELETE FROM media WHERE id LIKE 'test_%';
```

### 3. Test Incrementally

1. Test simple question first
2. Then test with parent_id
3. Then test with embeddings
4. Finally test edge cases

### 4. Monitor Logs

```bash
# Terminal 1: Watch FastAPI logs
docker-compose logs -f instachatico

# Terminal 2: Watch Celery logs
docker-compose logs -f celery_worker

# Terminal 3: Send test requests
curl -X POST ...
```

### 5. Use Descriptive Test IDs

```python
# Good ✅
"test_embedding_apartments_001"
"test_conversation_followup_002"
"test_ood_pizza_001"

# Bad ❌
"test1"
"abc123"
```

---

## Production Deployment

### Before Going to Production

1. **Set DEVELOPMENT_MODE=false**:
```bash
DEVELOPMENT_MODE=false
```

2. **Restart all services**:
```bash
docker-compose restart
```

3. **Verify webhook endpoint works**:
```bash
# Production webhook
POST /api/v1/webhook
# (with proper Instagram signature)
```

4. **Test endpoint should be disabled**:
```bash
# Should return 403
curl -X POST http://localhost:4291/api/v1/webhook/test \
  -H "Content-Type: application/json" \
  -d '{...}'

# Response: {"detail": "Test endpoint only accessible in DEVELOPMENT_MODE=true"}
```

5. **Clean test data from database**:
```sql
DELETE FROM instagram_comments WHERE id LIKE 'test_%' OR raw_data::text LIKE '%"test": true%';
DELETE FROM media WHERE id LIKE 'test_%';
```

---

## Security Considerations

### Development Mode Safety

- ✅ Test endpoint blocked in production (`DEVELOPMENT_MODE=false`)
- ✅ No real Instagram API calls made
- ✅ Database isolation (test IDs use `test_` prefix)
- ✅ Same authentication as main app
- ⚠️ Test data remains in database (clean regularly)

### Production Safety

- ✅ `DEVELOPMENT_MODE=false` disables test endpoint
- ✅ Real Instagram signature verification required
- ✅ All API calls go through Instagram
- ✅ No test data mixed with real data

---

## Advanced Usage

### Load Testing

```python
import concurrent.futures
import requests

def send_test_comment(i):
    return requests.post(
        "http://localhost:4291/api/v1/webhook/test",
        json={
            "comment_id": f"load_test_{i}",
            "media_id": "load_test_media",
            "user_id": f"user_{i}",
            "username": f"tester_{i}",
            "text": f"Test question number {i}?"
        }
    )

# Send 10 concurrent requests
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
    futures = [executor.submit(send_test_comment, i) for i in range(10)]
    results = [f.result() for f in futures]

print(f"Success: {sum(1 for r in results if r.status_code == 200)}/10")
```

### Integration Testing

```python
import pytest
import requests

BASE_URL = "http://localhost:4291"

def test_question_processing():
    response = requests.post(
        f"{BASE_URL}/api/v1/webhook/test",
        json={
            "comment_id": "pytest_001",
            "media_id": "pytest_media",
            "user_id": "pytest_user",
            "username": "pytest",
            "text": "Какие услуги вы предоставляете?"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["classification"] == "question / inquiry"
    assert data["answer"] is not None
    assert len(data["answer"]) > 0

def test_non_question():
    response = requests.post(
        f"{BASE_URL}/api/v1/webhook/test",
        json={
            "comment_id": "pytest_002",
            "media_id": "pytest_media",
            "user_id": "pytest_user",
            "username": "pytest",
            "text": "Отличная работа! 👍"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["classification"] == "positive feedback"
    assert data["answer"] is None
```

---

## Summary

✅ **Implemented**: Test endpoint `/api/v1/webhook/test`
✅ **Works in**: DEVELOPMENT_MODE=true only
✅ **Processes**: Full classification → answer pipeline
✅ **Skips**: Instagram API calls
✅ **Returns**: Answer in HTTP response
✅ **Creates**: All database records as in production

🎯 **Use this for**: 
- Testing AI agent responses
- Debugging classification logic
- Testing conversation threading
- Validating embedding search
- QA before production deployment

⚠️ **Remember**:
- Set `DEVELOPMENT_MODE=false` in production
- Clean test data regularly
- Monitor OpenAI API usage
- Keep test IDs unique

---

For detailed Postman examples, see `POSTMAN_TEST_PAYLOAD.md`

