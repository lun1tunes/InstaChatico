# Test Data Management - Implementation Summary

## 🎯 What Was Built

A complete test data management system for a **personal care products** Instagram business account.

---

## 📁 Files Created

### 1. Test Data Definitions
**`scripts/test_data/personal_care_products.py`**
- **35 realistic products** for a beauty/skincare business
- **5 test media posts** (Instagram posts with captions)
- Products in Russian with realistic prices, descriptions, categories
- Categories: Face care, hair care, body care, sun protection, sets, etc.

### 2. Data Management Scripts
**`scripts/load_test_data.py`** ✅
- Loads products into `product_embeddings` table
- Generates embeddings via OpenAI API
- Loads test media into `media` table
- Options: `--clean`, `--products-only`, `--media-only`
- Executable: `chmod +x`

**`scripts/clean_test_data.py`** ✅
- Removes test products, media, and comments
- Safety confirmation prompt
- Options: `--confirm`, `--products-only`, `--media-only`, `--comments-only`
- Executable: `chmod +x`

### 3. Documentation
**`docs/TEST_DATA_MANAGEMENT.md`** 📚
- Complete guide with examples
- Test scenarios and expected results
- Database queries
- Troubleshooting guide
- Integration with test endpoint

**`TEST_DATA_QUICKSTART.md`** 🚀
- Quick reference card
- Commands cheat sheet
- Common test queries
- One-page overview

---

## 🏗️ Architecture

```
Test Data Flow:

1. Load Phase
   personal_care_products.py
        ↓
   load_test_data.py
        ↓
   EmbeddingService.add_product()
        ↓
   OpenAI API (generate embeddings)
        ↓
   PostgreSQL (product_embeddings table)

2. Test Phase
   Test Endpoint Request
        ↓
   Agent processes comment
        ↓
   embedding_search tool
        ↓
   Query product_embeddings
        ↓
   Return high-confidence matches

3. Clean Phase
   clean_test_data.py
        ↓
   Delete from database
        ↓
   Clean state
```

---

## 📦 Data Content

### Products (35 items)

**Face Care (13 products)**:
- Cleansers: Foam cleanser, Salicylic gel, Micellar water
- Moisturizers: Vitamin E cream, Retinol night cream, Gel-cream
- Serums: Vitamin C, Hyaluronic, Niacinamide
- Masks: Clay mask, Sheet mask, Alginate mask
- Eye care: Eye cream with caffeine, Gold patches

**Hair Care (4 products)**:
- Keratin shampoo
- Moisturizing conditioner  
- Coconut hair mask
- Hair growth serum with biotin

**Body Care (4 products)**:
- Almond body lotion
- Coffee body scrub
- Shea hand cream
- Vanilla body oil

**Sun Protection (2 products)**:
- SPF 50 face cream
- Aloe after-sun spray

**Sets (3 products)**:
- Anti-age set 3-in-1
- Travel miniatures set
- SPA gift set

**Lip Care (2 products)**:
- Cocoa lip balm
- Mint lip scrub

**Nail Care (2 products)**:
- Nail strengthening serum
- Jojoba cuticle oil

**Price Range**: 390 ₽ - 4,990 ₽

### Test Media (5 posts)

1. **Skincare post** - Vitamin C serum launch
2. **Hair care post** - Summer recovery products
3. **Promotion post** - 20% discount on sets
4. **Body care post** - Coffee scrub showcase
5. **Routine post** - Evening skincare guide

---

## 🚀 Usage Guide

### Initial Setup (One Time)

```bash
cd /var/www/instachatico/app

# Load all test data
python scripts/load_test_data.py
```

**Output**:
```
================================================================================
                          Loading Product Embeddings
================================================================================

✅ [1/35] Added: Нежная пенка для умывания...
✅ [2/35] Added: Гель для умывания с салициловой кислотой...
...
✅ [35/35] Added: Масло для кутикулы с маслом жожоба

Products loaded: 35

================================================================================
                            Loading Test Media
================================================================================

✅ [1/5] Added: test_media_skincare_001
✅ [2/5] Added: test_media_hair_001
...

Media records loaded: 5

✅ All data loaded successfully! 🎉
```

### Testing Products

```bash
# Test with semantic search
python scripts/test_ood_detection.py

# Test with endpoint
curl -X POST http://localhost:4291/api/v1/webhook/test \
  -H "Content-Type: application/json" \
  -d '{
    "comment_id": "test_product_search",
    "media_id": "test_media_skincare_001",
    "user_id": "user_001",
    "username": "test_customer",
    "text": "Какие у вас есть сыворотки для лица?"
  }'
```

**Expected Response**:
```json
{
  "status": "success",
  "classification": "question / inquiry",
  "confidence": 95,
  "answer": "У нас есть несколько отличных сывороток для лица:\n\n1. Сыворотка с витамином С (2,490₽) - для сияния и осветления пигментации\n2. Гиалуроновая сыворотка (2,190₽) - для глубокого увлажнения\n3. Ниацинамид сыворотка (1,790₽) - для сужения пор...",
  "answer_confidence": 0.92,
  "answer_quality_score": 88
}
```

### Daily Cleanup

```bash
# Clean only test comments (keeps products and media)
python scripts/clean_test_data.py --comments-only --confirm
```

### Complete Reset

```bash
# Clean everything
python scripts/clean_test_data.py --confirm

# Reload
python scripts/load_test_data.py
```

---

## 🧪 Test Scenarios

### ✅ Scenario 1: Specific Product Type

**Query**: "Какие сыворотки для лица у вас есть?"

**Agent Behavior**:
1. Classification: "question / inquiry"
2. Calls `embedding_search(query="сыворотки для лица")`
3. Finds 3 products (Vitamin C, Hyaluronic, Niacinamide)
4. Returns detailed answer with prices

### ✅ Scenario 2: Category Search

**Query**: "Покажите маски для лица"

**Agent Behavior**:
1. Searches category "Маски для лица"
2. Finds 3 types of masks
3. Describes each with benefits

### ✅ Scenario 3: OOD Detection

**Query**: "Вы продаете детские игрушки?"

**Agent Behavior**:
1. Searches embeddings
2. All results < 70% threshold
3. Returns "NO RELEVANT PRODUCTS FOUND"
4. Agent politely says "We don't sell toys"

### ✅ Scenario 4: Price Inquiry

**Query**: "Сколько стоит крем с ретинолом?"

**Agent Behavior**:
1. Finds "Ночной восстанавливающий крем с ретинолом"
2. Returns price: "2,890 ₽"
3. Includes product benefits

### ✅ Scenario 5: Gift Set

**Query**: "Подарочный набор есть?"

**Agent Behavior**:
1. Finds 3 sets (Anti-age, Travel, SPA)
2. Describes each set
3. Mentions gift packaging

---

## 🔄 Integration with Test Endpoint

The test data integrates seamlessly with the test endpoint:

```bash
# 1. Products are searched automatically by agent
curl -X POST http://localhost:4291/api/v1/webhook/test \
  -d '{"text": "Какие кремы для лица есть?", ...}'

# 2. Media provides context
curl -X POST http://localhost:4291/api/v1/webhook/test \
  -d '{"media_id": "test_media_hair_001", "text": "Что это за продукт?", ...}'

# 3. Conversation threading works
curl -X POST http://localhost:4291/api/v1/webhook/test \
  -d '{"parent_id": "previous_comment", "text": "А цена?", ...}'
```

---

## 📊 Database Schema

### product_embeddings Table
```sql
CREATE TABLE product_embeddings (
    id SERIAL PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    description TEXT NOT NULL,
    category VARCHAR(100),
    price VARCHAR(100),
    embedding vector(1536),  -- OpenAI embeddings
    tags TEXT,
    url VARCHAR(500),
    image_url VARCHAR(500),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### Sample Data
```sql
SELECT id, title, category, price 
FROM product_embeddings 
LIMIT 3;

-- Results:
-- 1 | Нежная пенка для умывания... | Уход за лицом | 1,290 ₽
-- 2 | Гель для умывания... | Уход за лицом | 1,450 ₽
-- 3 | Мицеллярная вода... | Уход за лицом | 890 ₽
```

---

## 🎨 Customization

### Add Your Own Products

Edit `scripts/test_data/personal_care_products.py`:

```python
PERSONAL_CARE_PRODUCTS = [
    # ... existing products ...
    {
        "title": "Ваш новый продукт",
        "description": "Подробное описание продукта с ключевыми словами",
        "category": "Категория",
        "price": "1,990 ₽",
        "tags": "тег1, тег2, тег3",
        "url": "https://example.com/product",
        "image_url": "https://example.com/image.jpg",
    },
]
```

Then reload:
```bash
python scripts/load_test_data.py --products-only
```

### Add Test Media

```python
MEDIA_TEST_DATA = [
    # ... existing media ...
    {
        "id": "test_media_new_001",
        "caption": "Ваш пост в Instagram с описанием...",
        "media_type": "IMAGE",
        "username": "beauty_care_shop",
        # ... other fields
    },
]
```

Reload:
```bash
python scripts/load_test_data.py --media-only
```

---

## 🛡️ Best Practices

### ✅ DO

1. **Keep products loaded** - Load once, reuse many times
2. **Clean comments regularly** - `--comments-only` after testing
3. **Use test prefixes** - All test IDs start with `test_` or `conv_`
4. **Realistic descriptions** - Better embeddings, better search
5. **Version control** - Commit Python data files to git

### ❌ DON'T

1. **Don't mix with production** - Always use test prefixes
2. **Don't delete products daily** - They're meant to persist
3. **Don't commit database dumps** - Only Python source files
4. **Don't skip embeddings** - Always use the loader script

---

## 🔍 Verification

### Check Products Loaded

```bash
# Quick check
docker exec postgres psql -U lun1z -d instagram_db -c \
  "SELECT COUNT(*), category FROM product_embeddings GROUP BY category;"

# Expected output:
# count | category
#-------+------------------
#    13 | Уход за лицом
#     4 | Уход за волосами
#     4 | Уход за телом
#     3 | Наборы
#     2 | Солнцезащита
#     2 | Уход за глазами
#     2 | Уход за губами
#     2 | Уход за ногтями
#     3 | Маски для лица
```

### Test Embeddings Work

```bash
python scripts/test_ood_detection.py
```

Expected: All tests pass ✅

---

## 📞 Production Readiness

### Before Production Deployment

```bash
# 1. Clean ALL test data
python scripts/clean_test_data.py --confirm

# 2. Verify database is clean
python scripts/clean_test_data.py
# Output: "No test data found. Database is clean! ✨"

# 3. Load real products (create your own script)
python scripts/load_production_products.py

# 4. Set DEVELOPMENT_MODE=false
sed -i 's/DEVELOPMENT_MODE=true/DEVELOPMENT_MODE=false/' .env

# 5. Restart services
docker-compose restart
```

---

## 📚 Documentation

| File | Purpose |
|------|---------|
| `TEST_DATA_QUICKSTART.md` | Quick reference (this is your starting point!) |
| `docs/TEST_DATA_MANAGEMENT.md` | Complete guide with all details |
| `docs/DEVELOPMENT_MODE_TESTING.md` | Test endpoint documentation |
| `docs/EMBEDDING_SEARCH.md` | Embedding search system |
| `docs/POSTMAN_TEST_PAYLOAD.md` | Postman examples |

---

## 🎓 Learning Resources

### Understanding the Flow

1. **Load products** → Creates embeddings via OpenAI
2. **User asks question** → Agent searches products
3. **Semantic search** → Finds relevant products (cosine similarity)
4. **OOD detection** → Filters low-confidence results (< 70%)
5. **Agent responds** → Natural language answer with product details

### Key Concepts

- **Embeddings**: 1536-dimensional vectors representing semantic meaning
- **Cosine Similarity**: Measures how similar two vectors are (0-1)
- **OOD Detection**: Filters out irrelevant results (threshold: 0.7)
- **Test Prefix**: Naming convention (`test_*`) to separate test data

---

## 🚀 Quick Start Recap

```bash
# 1. Load test data (one time)
python scripts/load_test_data.py

# 2. Test products work
python scripts/test_ood_detection.py

# 3. Test with endpoint
curl -X POST http://localhost:4291/api/v1/webhook/test \
  -H "Content-Type: application/json" \
  -d '{"comment_id":"t1","media_id":"test_media_skincare_001","user_id":"u1","username":"test","text":"Какие сыворотки есть?"}'

# 4. Clean test comments when done
python scripts/clean_test_data.py --comments-only --confirm
```

---

## ✅ Summary

You now have:
- ✅ **35 realistic products** for personal care business
- ✅ **5 test media posts** with Instagram-style captions
- ✅ **Load script** to populate database with embeddings
- ✅ **Clean script** to remove test data safely
- ✅ **Complete documentation** with examples and troubleshooting
- ✅ **Integration** with test endpoint for full pipeline testing
- ✅ **OOD detection** to prevent hallucinations
- ✅ **Best practices** and production readiness guide

**Everything is in `scripts/` folder and is ready to use!** 🎉

---

**Next Steps**: Run `python scripts/load_test_data.py` and start testing! 🚀

