# Test Data Management

Complete guide for managing test data (products, media, comments) in development mode.

---

## Overview

Test data consists of:
1. **Product Embeddings** - Personal care products with vector embeddings for semantic search
2. **Test Media** - Instagram media records (posts) for context
3. **Test Comments** - Comments created via test endpoint

---

## Quick Start

### Load Test Data

```bash
# Load all test data (products + media)
python scripts/load_test_data.py

# Clean old data and reload
python scripts/load_test_data.py --clean
```

### Clean Test Data

```bash
# Clean all test data (with confirmation)
python scripts/clean_test_data.py

# Clean without confirmation
python scripts/clean_test_data.py --confirm

# Clean only specific data
python scripts/clean_test_data.py --products-only
python scripts/clean_test_data.py --media-only
python scripts/clean_test_data.py --comments-only
```

---

## Test Data Structure

### 1. Products (35 items)

**Location**: `scripts/test_data/personal_care_products.py`

**Categories**:
- Уход за лицом (Face Care) - cleansers, moisturizers, serums
- Маски для лица (Face Masks)
- Уход за глазами (Eye Care)
- Уход за волосами (Hair Care)
- Уход за телом (Body Care)
- Солнцезащита (Sun Protection)
- Наборы (Sets & Kits)
- Уход за губами (Lip Care)
- Уход за ногтями (Nail Care)

**Example Product**:
```python
{
    "title": "Сыворотка с витамином С для сияния кожи",
    "description": "Концентрированная сыворотка с 15% витамином С...",
    "category": "Уход за лицом",
    "price": "2 490 ₽",
    "tags": "сыворотка, витамин C, сияние кожи...",
    "url": "https://example.com/products/vitamin-c-serum",
    "image_url": "https://example.com/images/vitamin-c-serum.jpg"
}
```

### 2. Test Media (5 items)

**Sample Media IDs**:
- `test_media_skincare_001` - Skincare products post
- `test_media_hair_001` - Hair care products
- `test_media_promotion_001` - Promotional post with discount
- `test_media_body_care_001` - Body care post
- `test_media_routine_001` - Skincare routine guide

**Example Media**:
```python
{
    "id": "test_media_skincare_001",
    "caption": "✨ Новинка! Сыворотка с витамином С...",
    "media_type": "IMAGE",
    "username": "beauty_care_shop",
    "comments_count": 45,
    "like_count": 320
}
```

### 3. Test Comments

Created via test endpoint, not pre-loaded. Use format: `test_*` or `conv_*` prefix.

---

## Scripts Reference

### `load_test_data.py`

Loads products and media into the database.

**Usage**:
```bash
python scripts/load_test_data.py [OPTIONS]
```

**Options**:
- `--clean` - Remove existing data before loading
- `--products-only` - Load only products (skip media)
- `--media-only` - Load only media (skip products)

**Examples**:
```bash
# First time setup
python scripts/load_test_data.py

# Reload everything fresh
python scripts/load_test_data.py --clean

# Add more products without touching media
python scripts/load_test_data.py --products-only
```

**Output**:
```
================================================================================
                          Loading Product Embeddings
================================================================================

ℹ️  Loading 35 products...
✅ [1/35] Added: Нежная пенка для умывания с гиалуроновой кислотой
✅ [2/35] Added: Гель для умывания с салициловой кислотой...
...

Products loaded: 35
Media records loaded: 5

✅ All data loaded successfully! 🎉
```

---

### `clean_test_data.py`

Removes test data from database.

**Usage**:
```bash
python scripts/clean_test_data.py [OPTIONS]
```

**Options**:
- `--confirm` - Skip confirmation prompt
- `--products-only` - Clean only products
- `--media-only` - Clean only test media
- `--comments-only` - Clean only test comments

**Examples**:
```bash
# Clean everything (interactive)
python scripts/clean_test_data.py

# Clean without prompt (for scripts)
python scripts/clean_test_data.py --confirm

# Clean only test comments
python scripts/clean_test_data.py --comments-only --confirm
```

**Safety**:
- Always asks for confirmation (unless `--confirm`)
- Shows count before deleting
- Only deletes test records (media with `test_*` prefix)

---

## Typical Workflows

### 1. Initial Setup

```bash
# 1. Load test data
python scripts/load_test_data.py

# 2. Verify embeddings work
python scripts/test_ood_detection.py

# 3. Test with endpoint
curl -X POST http://localhost:4291/api/v1/webhook/test \
  -H "Content-Type: application/json" \
  -d '{
    "comment_id": "test_001",
    "media_id": "test_media_skincare_001",
    "user_id": "user_001",
    "username": "customer",
    "text": "Какие сыворотки у вас есть?"
  }'
```

### 2. Daily Development

```bash
# Test endpoint creates comments automatically
# Clean only comments when needed
python scripts/clean_test_data.py --comments-only --confirm

# Products and media stay for reuse
```

### 3. Complete Reset

```bash
# Remove everything
python scripts/clean_test_data.py --confirm

# Reload fresh
python scripts/load_test_data.py
```

### 4. Before Production

```bash
# Clean all test data
python scripts/clean_test_data.py --confirm

# Verify database is clean
python scripts/clean_test_data.py
# Should show: "No test data found. Database is clean! ✨"
```

---

## Test Scenarios

### Scenario 1: Product Search Question

**Comment**:
```json
{
  "comment_id": "test_search_001",
  "media_id": "test_media_skincare_001",
  "text": "Какие у вас есть сыворотки для лица?"
}
```

**Expected**:
- Classification: "question / inquiry"
- Agent uses `embedding_search` tool
- Finds: Vitamin C serum, Hyaluronic serum, Niacinamide serum
- Returns detailed answer with prices

### Scenario 2: Specific Product Inquiry

**Comment**:
```json
{
  "text": "Сколько стоит крем с ретинолом?"
}
```

**Expected**:
- Finds "Ночной восстанавливающий крем с ретинолом"
- Answer includes price: "2 890 ₽"

### Scenario 3: OOD Detection

**Comment**:
```json
{
  "text": "Вы продаете детские игрушки?"
}
```

**Expected**:
- Classification: "question / inquiry"
- `embedding_search` returns "NO RELEVANT PRODUCTS FOUND"
- Agent politely says "No, we don't sell toys"

### Scenario 4: Category Search

**Comment**:
```json
{
  "text": "Покажите маски для лица"
}
```

**Expected**:
- Finds products from "Маски для лица" category
- Returns: Clay mask, Sheet mask, Alginate mask

### Scenario 5: Hair Care

**Comment**:
```json
{
  "media_id": "test_media_hair_001",
  "text": "Подскажите, есть ли у вас средства для роста волос?"
}
```

**Expected**:
- Uses media context (hair care post)
- Finds "Сыворотка для роста волос с биотином"
- Relevant answer with product details

---

## Database Queries

### Check Loaded Data

```sql
-- Count products
SELECT COUNT(*) FROM product_embeddings;

-- List products by category
SELECT category, COUNT(*) 
FROM product_embeddings 
GROUP BY category 
ORDER BY COUNT(*) DESC;

-- Check test media
SELECT id, caption, comments_count, like_count 
FROM media 
WHERE id LIKE 'test_%';

-- Check test comments
SELECT ic.id, ic.text, cc.classification, qa.answer IS NOT NULL as has_answer
FROM instagram_comments ic
LEFT JOIN comments_classification cc ON cc.comment_id = ic.id
LEFT JOIN question_messages_answers qa ON qa.comment_id = ic.id
WHERE ic.id LIKE 'test_%'
ORDER BY ic.created_at DESC
LIMIT 10;
```

### Verify Embeddings

```sql
-- Check embedding dimensions
SELECT id, title, 
       array_length(embedding, 1) as dimensions,
       category, price
FROM product_embeddings 
LIMIT 5;

-- Search by category
SELECT title, price 
FROM product_embeddings 
WHERE category = 'Уход за лицом'
ORDER BY title;
```

### Clean Specific Records

```sql
-- Delete comments from specific test
DELETE FROM instagram_comments 
WHERE id LIKE 'test_scenario_%';

-- Keep only recent test data
DELETE FROM instagram_comments 
WHERE id LIKE 'test_%' 
  AND created_at < NOW() - INTERVAL '7 days';
```

---

## Adding Your Own Test Data

### Method 1: Edit Python File

Edit `scripts/test_data/personal_care_products.py`:

```python
PERSONAL_CARE_PRODUCTS = [
    # ... existing products ...
    {
        "title": "Your New Product",
        "description": "Detailed description here...",
        "category": "Уход за лицом",
        "price": "1 990 ₽",
        "tags": "tag1, tag2, tag3",
        "url": "https://example.com/product",
        "image_url": "https://example.com/image.jpg",
    },
]
```

Then reload:
```bash
python scripts/load_test_data.py --products-only
```

### Method 2: Direct API Call

Use the embedding service directly:

```python
from core.services.embedding_service import EmbeddingService

async def add_custom_product():
    service = EmbeddingService()
    await service.add_product(
        title="Custom Product",
        description="Description...",
        session=session,
        category="Category",
        price="1000 ₽"
    )
```

### Method 3: SQL Import

```sql
-- Note: You need to generate embeddings separately
INSERT INTO product_embeddings (title, description, category, price, embedding)
VALUES (
    'Product Title',
    'Description',
    'Category',
    '1000 ₽',
    array_fill(0::float, ARRAY[1536])  -- Dummy embedding
);
```

---

## Best Practices

### ✅ DO

1. **Use prefixes** - All test IDs should start with `test_` or `conv_`
2. **Clean regularly** - Remove old test comments weekly
3. **Keep products** - Products and media can be reused
4. **Realistic data** - Use realistic product descriptions for better testing
5. **Version control** - Commit test data files to git

### ❌ DON'T

1. **Don't mix test and real data** - Always use test prefixes
2. **Don't delete products before testing** - Keep products loaded
3. **Don't commit database dumps** - Only commit Python data files
4. **Don't use production data** - Use only test data in development

---

## Troubleshooting

### Products not found in search

**Symptoms**: Embedding search returns "NO RELEVANT PRODUCTS FOUND" for valid queries

**Causes**:
1. Products not loaded
2. Embedding threshold too high
3. OpenAI API error during embedding generation

**Fix**:
```bash
# Check if products exist
python scripts/verify_embedding_setup.py

# Reload products
python scripts/load_test_data.py --clean --products-only

# Lower threshold temporarily
export EMBEDDING_SIMILARITY_THRESHOLD=0.6
```

### "Permission denied" error

**Fix**:
```bash
chmod +x scripts/load_test_data.py scripts/clean_test_data.py
```

### OpenAI API rate limit

**Symptoms**: Errors during product loading

**Fix**:
```python
# In personal_care_products.py, split into batches
# Load in smaller chunks:
python scripts/load_test_data.py --products-only
# Wait 60 seconds
python scripts/load_test_data.py --products-only
```

### Database connection error

**Fix**:
```bash
# Check database is running
docker-compose ps postgres

# Test connection
docker exec postgres psql -U lun1z -d instagram_db -c "SELECT 1"
```

---

## File Structure

```
scripts/
├── test_data/
│   └── personal_care_products.py   # Test data definitions
├── load_test_data.py               # Loader script
├── clean_test_data.py              # Cleanup script
├── test_ood_detection.py           # Test embeddings
└── test_development_endpoint.py    # Test endpoint

docs/
└── TEST_DATA_MANAGEMENT.md         # This file
```

---

## Integration with Test Endpoint

The test endpoint automatically uses:
- **Media**: Provide `media_id` from test media (e.g., `test_media_skincare_001`)
- **Products**: Agent searches via `embedding_search` tool
- **Comments**: Created on-the-fly with test IDs

**Example Integration**:
```bash
# 1. Load test data
python scripts/load_test_data.py

# 2. Use test endpoint
curl -X POST http://localhost:4291/api/v1/webhook/test \
  -H "Content-Type: application/json" \
  -d '{
    "comment_id": "test_integration_001",
    "media_id": "test_media_skincare_001",
    "user_id": "user_001",
    "username": "test_customer",
    "text": "Какой крем для лица вы посоветуете?"
  }'

# 3. Clean test comments (keep products/media)
python scripts/clean_test_data.py --comments-only --confirm
```

---

## Maintenance Schedule

### Daily
- Clean test comments: `python scripts/clean_test_data.py --comments-only --confirm`

### Weekly
- Review and clean old test data
- Update products if needed

### Before Deployment
- Clean ALL test data: `python scripts/clean_test_data.py --confirm`
- Verify: `python scripts/clean_test_data.py` (should show "clean")

---

## Summary

✅ **Load test data**: `python scripts/load_test_data.py`
✅ **Clean test data**: `python scripts/clean_test_data.py`
✅ **Test products**: Use test endpoint or OOD detection script
✅ **Keep organized**: Use `test_` prefixes for all test records

For more information:
- Test endpoint: `docs/DEVELOPMENT_MODE_TESTING.md`
- Embedding search: `docs/EMBEDDING_SEARCH.md`
- Postman examples: `docs/POSTMAN_TEST_PAYLOAD.md`

