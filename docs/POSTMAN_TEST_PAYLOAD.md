# Test Endpoint - Postman Examples

## Endpoint Details

**URL**: `POST /api/v1/webhook/test`

**Requirements**: 
- `DEVELOPMENT_MODE=true` in `.env` file
- All services running (FastAPI, PostgreSQL, Redis, Celery workers)

**Authentication**: None (inherits from main app settings)

---

## Test Payload Examples

### Example 1: Simple Question

```json
{
  "comment_id": "test_comment_001",
  "media_id": "test_media_001",
  "user_id": "test_user_123",
  "username": "test_customer",
  "text": "Какие у вас есть квартиры в центре города?",
  "media_caption": "Новые квартиры в центре! 🏢"
}
```

**Expected Response**:
```json
{
  "status": "success",
  "comment_id": "test_comment_001",
  "classification": "question / inquiry",
  "confidence": 95,
  "reasoning": "Customer is asking about available apartments in the city center",
  "answer": "У нас есть несколько вариантов квартир в центре города...",
  "answer_confidence": 0.92,
  "answer_quality_score": 88,
  "processing_details": {
    "classification_result": {...},
    "answer_result": {...}
  }
}
```

---

### Example 2: Product Question (with Embedding Search)

```json
{
  "comment_id": "test_comment_002",
  "media_id": "test_media_001",
  "user_id": "test_user_456",
  "username": "interested_buyer",
  "text": "Сколько стоит консультация по недвижимости?",
  "media_caption": "Профессиональные консультации по покупке недвижимости"
}
```

This should trigger the `embedding_search` tool if you have products in the database.

---

### Example 3: Reply to Comment (Thread Testing)

```json
{
  "comment_id": "test_comment_003",
  "media_id": "test_media_001",
  "user_id": "test_user_123",
  "username": "test_customer",
  "text": "А есть с балконом?",
  "parent_id": "test_comment_001",
  "media_caption": "Новые квартиры в центре! 🏢"
}
```

This tests conversation continuity - the agent will use context from `parent_id`.

---

### Example 4: Positive Feedback (Non-Question)

```json
{
  "comment_id": "test_comment_004",
  "media_id": "test_media_002",
  "user_id": "test_user_789",
  "username": "happy_client",
  "text": "Отличный сервис! Все прошло замечательно, спасибо! 😊",
  "media_caption": "Рады помочь нашим клиентам!"
}
```

**Expected**: Classification as "positive feedback", no answer generated.

---

### Example 5: Critical Feedback

```json
{
  "comment_id": "test_comment_005",
  "media_id": "test_media_002",
  "user_id": "test_user_999",
  "username": "concerned_customer",
  "text": "Качество не соответствует описанию, очень разочарован",
  "media_caption": "Наш каталог услуг"
}
```

**Expected**: Classification as "critical feedback", Telegram notification triggered (but no answer).

---

### Example 6: Spam/Irrelevant

```json
{
  "comment_id": "test_comment_006",
  "media_id": "test_media_002",
  "user_id": "spammer_001",
  "username": "spam_bot_123",
  "text": "🔥🔥🔥 BEST CRYPTO INVESTMENT!!! Click link in bio!!! 💰💰💰",
  "media_caption": "Наши услуги"
}
```

**Expected**: Classification as "spam / irrelevant", no further processing.

---

## Postman Setup

### Step 1: Create New Request

1. Open Postman
2. Create new request: `POST`
3. URL: `http://localhost:4291/api/v1/webhook/test`
4. Headers:
   - `Content-Type: application/json`

### Step 2: Body

Select **Body** → **raw** → **JSON**, then paste one of the examples above.

### Step 3: Send

Click **Send** and observe the response.

---

## Testing Checklist

- [ ] Set `DEVELOPMENT_MODE=true` in `.env`
- [ ] Restart FastAPI (`docker-compose restart instachatico`)
- [ ] Verify Celery workers are running
- [ ] Test simple question (Example 1)
- [ ] Test with parent_id (Example 3)
- [ ] Test non-question classifications (Examples 4-6)
- [ ] Verify no Instagram API calls are made (check logs)
- [ ] Verify database records are created (check PostgreSQL)

---

## Verification

### Check Database Records

```sql
-- Check comment
SELECT * FROM instagram_comments WHERE id = 'test_comment_001';

-- Check classification
SELECT * FROM comments_classification WHERE comment_id = 'test_comment_001';

-- Check answer (for questions only)
SELECT * FROM question_messages_answers WHERE comment_id = 'test_comment_001';

-- Check reply status
SELECT 
  ic.id,
  ic.text,
  cc.classification,
  qa.answer,
  qa.reply_sent,
  qa.reply_status
FROM instagram_comments ic
LEFT JOIN comments_classification cc ON cc.comment_id = ic.id
LEFT JOIN question_messages_answers qa ON qa.comment_id = ic.id
WHERE ic.id LIKE 'test_comment_%'
ORDER BY ic.created_at DESC;
```

### Check Logs

```bash
# Watch FastAPI logs
docker-compose logs -f instachatico

# Watch Celery logs
docker-compose logs -f celery_worker

# Look for these messages:
# ✅ "DEVELOPMENT_MODE: Skipping Instagram API call"
# ✅ "Processing test comment: test_comment_XXX"
# ✅ "Test comment processing complete"
```

---

## Error Responses

### DEVELOPMENT_MODE=false

```json
{
  "detail": "Test endpoint only accessible in DEVELOPMENT_MODE=true"
}
```

**HTTP Status**: 403

**Fix**: Set `DEVELOPMENT_MODE=true` in `.env` and restart services.

---

### Classification Failed

```json
{
  "detail": "Classification failed: media_data_unavailable"
}
```

**HTTP Status**: 500

**Fix**: Check OpenAI API key, database connection, and Celery workers.

---

## Advanced Usage

### Testing OOD Detection

First, populate some products:

```bash
python scripts/populate_embeddings.py
```

Then test with irrelevant query:

```json
{
  "comment_id": "test_ood_001",
  "media_id": "test_media_003",
  "user_id": "test_user_111",
  "username": "pizza_lover",
  "text": "Вы продаете пиццу?",
  "media_caption": "Наши услуги по недвижимости"
}
```

**Expected**: Answer should politely say "We don't sell pizza" (OOD detected).

---

### Testing Conversation Context

1. Send first question:
```json
{
  "comment_id": "conv_001",
  "media_id": "test_media_004",
  "user_id": "user_999",
  "username": "buyer_alex",
  "text": "Расскажите о квартирах в центре",
  "media_caption": "Новостройки 2025"
}
```

2. Send follow-up (reply):
```json
{
  "comment_id": "conv_002",
  "media_id": "test_media_004",
  "user_id": "user_999",
  "username": "buyer_alex",
  "text": "А цена?",
  "parent_id": "conv_001",
  "media_caption": "Новостройки 2025"
}
```

**Expected**: Second answer uses context from first question.

---

## Cleanup Test Data

```sql
-- Delete all test comments
DELETE FROM instagram_comments WHERE id LIKE 'test_%' OR id LIKE 'conv_%';

-- Delete test media
DELETE FROM media WHERE id LIKE 'test_%';
```

---

## Tips

1. **Use unique comment_ids** for each test to avoid conflicts
2. **Same media_id** can be reused for multiple comments
3. **parent_id** must reference an existing comment for threading
4. **Media caption** provides context to the AI agent
5. **Watch logs** to see agent decision-making process

---

## Production vs Development

| Feature | DEVELOPMENT_MODE=false | DEVELOPMENT_MODE=true |
|---------|------------------------|------------------------|
| `/api/v1/webhook/test` | ❌ 403 Forbidden | ✅ Accessible |
| Instagram API calls | ✅ Sent | ❌ Skipped |
| Database records | ✅ Created | ✅ Created |
| Answer in response | ❌ No | ✅ Yes |
| Telegram notifications | ✅ Sent | ✅ Sent (if configured) |
| Celery tasks | ✅ Queued | ✅ Queued |

---

## Quick Start

```bash
# 1. Enable development mode
echo "DEVELOPMENT_MODE=true" >> .env

# 2. Restart services
cd docker
docker-compose restart instachatico celery_worker

# 3. Send test request
curl -X POST http://localhost:4291/api/v1/webhook/test \
  -H "Content-Type: application/json" \
  -d '{
    "comment_id": "quick_test_001",
    "media_id": "media_001",
    "user_id": "user_001",
    "username": "test_user",
    "text": "Какие услуги вы предоставляете?"
  }'

# 4. Check response (should return classification + answer)
```

---

## Troubleshooting

### No answer generated

**Possible causes**:
- Comment not classified as "question / inquiry"
- Classification failed (check logs)
- OpenAI API error
- Celery workers not running

**Check**:
```bash
docker-compose ps  # All services should be "Up"
docker-compose logs celery_worker  # Check for errors
```

### Timeout error

**Cause**: Classification or answer generation takes too long

**Solution**: Increase request timeout in Postman or use async webhook flow instead

---

For more information, see the main README.md

