# OOD Detection Implementation Summary

## Problem Statement

**Initial Issue**: Without OOD (Out-of-Distribution) detection, the embedding search would return the "closest" matches even for completely irrelevant queries, potentially causing the agent to provide incorrect information.

**Example**:
- Customer: "Do you sell pizza?"
- Old behavior: Returns "Penthouse apartment" (35% similarity)
- Agent response: Might use this irrelevant data ❌

## Solution Implemented

### 1. **Automatic Filtering** ✅

The system now **automatically filters** all results below 70% similarity threshold:

```python
# In embedding_search_tool.py
high_confidence = [r for r in results if not r['is_ood']]  # >= 70%
low_confidence = [r for r in results if r['is_ood']]       # < 70%

if not high_confidence:
    return "⚠️ NO RELEVANT PRODUCTS FOUND"
```

### 2. **Clear OOD Messages** ✅

When no high-confidence matches found, returns explicit message:

```
⚠️ NO RELEVANT PRODUCTS FOUND

Your query 'pizza' did not match any products/services in our catalog.
The search found 3 result(s), but the best match had only 35.2% similarity (threshold: 70%).

This means we likely don't offer products/services related to 'pizza'.
Please inform the customer politely that this specific item/service is not available.

💡 Suggestion: Ask the customer to clarify their request or check what we actually offer.
```

### 3. **Agent Instructions Updated** ✅

Agent now understands three possible outcomes:

**A) High-Confidence Results** (≥ 70%)
```
✅ Found 3 relevant result(s):
[1] Квартира в центре (confidence: 92%)
...
```
→ Agent uses this information safely ✅

**B) OOD - Not Found** (< 70%)
```
⚠️ NO RELEVANT PRODUCTS FOUND
(best match: 35%)
```
→ Agent politely declines and suggests alternatives ✅

**C) Empty Database**
```
⚠️ DATABASE EMPTY
```
→ Agent apologizes and provides contact info ✅

### 4. **Configurable Threshold** ✅

Added environment variable for easy tuning:

```bash
# In .env
EMBEDDING_SIMILARITY_THRESHOLD=0.7  # Default: 70%
```

Adjust based on your needs:
- `0.8` - Stricter filtering (fewer false positives)
- `0.7` - Balanced (recommended)
- `0.6` - More lenient (fewer false negatives)

## How OOD Detection Works

### Step 1: Semantic Search
```
Query: "pizza" → OpenAI Embedding → [0.123, -0.456, ...]
                                      ↓
                            Cosine Similarity Search
                                      ↓
                    All results with similarity scores:
                    - Penthouse: 0.35 (35%)
                    - Apartment: 0.32 (32%)
                    - Cottage: 0.28 (28%)
```

### Step 2: OOD Filtering
```python
threshold = 0.7  # 70%

for result in all_results:
    if result['similarity'] >= threshold:
        high_confidence.append(result)  # KEEP
    else:
        low_confidence.append(result)   # FILTER OUT (OOD)
```

### Step 3: Decision
```
if high_confidence:
    return high_confidence  # Return good matches
else:
    return "NO RELEVANT PRODUCTS FOUND"  # All filtered as OOD
```

## Benefits

### ✅ Prevents False Information
- Agent won't invent products that don't exist
- No more "closest match" mistakes
- Clear "not available" responses

### ✅ Improves User Experience
- Honest answers build trust
- Customers get accurate information
- Reduces confusion and complaints

### ✅ Measurable Quality
- Confidence scores visible: "92%" vs "35%"
- Clear threshold: Below 70% = not relevant
- Testable: Run `test_ood_detection.py`

### ✅ Easy to Tune
- Environment variable configuration
- Test different thresholds
- Monitor and adjust based on real queries

## Testing

### Run OOD Tests
```bash
python scripts/test_ood_detection.py
```

**Expected Results**:
- ✅ High-confidence queries return results
- ✅ OOD queries return "not found"
- ✅ 90%+ pass rate

**Sample Test Cases**:

| Query | Expected | Result | Status |
|-------|----------|--------|--------|
| "квартиры в центре" | HIGH_CONFIDENCE | Found 3 results (85-92%) | ✅ PASS |
| "недвижимость" | HIGH_CONFIDENCE | Found 5 results (78-91%) | ✅ PASS |
| "пицца" | OOD | No relevant products (35%) | ✅ PASS |
| "автомобили" | OOD | No relevant products (28%) | ✅ PASS |

## Verification

### Quick Check
```bash
python scripts/verify_embedding_setup.py
```

### Manual Test
```python
from core.services.embedding_service import EmbeddingService

service = EmbeddingService()

# Test 1: Relevant query (should return results)
results = await service.search_similar_products(
    query="квартиры",
    session=session
)
# Expected: high_confidence results with similarity >= 0.7

# Test 2: Irrelevant query (should filter all as OOD)
results = await service.search_similar_products(
    query="pizza",
    session=session
)
# Expected: All results have is_ood=True, filtered by tool
```

## Files Modified

### Core Implementation
1. **`src/core/agents/tools/embedding_search_tool.py`**
   - Added OOD filtering logic
   - Returns clear "not found" messages
   - Filters results before returning to agent

2. **`src/core/services/embedding_service.py`**
   - Calculates similarity scores
   - Marks OOD results (similarity < threshold)
   - Uses configurable threshold from settings

3. **`src/core/config.py`**
   - Added `EmbeddingSettings` class
   - Configurable via environment variables

### Agent Instructions
4. **`src/core/agents/instructions/instruction_response.py`**
   - Detailed tool usage examples
   - Scenario-based guidance
   - Clear handling of OOD responses

### Testing & Documentation
5. **`scripts/test_ood_detection.py`** - Comprehensive OOD tests
6. **`scripts/verify_embedding_setup.py`** - Setup verification
7. **`docs/EMBEDDING_SEARCH.md`** - Full documentation
8. **`docs/OOD_DETECTION_SUMMARY.md`** - This file

## Real-World Examples

### Example 1: Relevant Query ✅
```
Customer: "Какие у вас квартиры в центре?"

Tool output:
✅ Found 3 relevant result(s) for query: 'квартиры в центре'

[1] Квартира в центре (confidence: 92%)
Description: Просторная двухкомнатная квартира...
Price: 5 000 000 руб.

[2] Апартаменты у моря (confidence: 85%)
...

Agent response:
"У нас есть несколько отличных вариантов квартир в центре!
Например, просторная двухкомнатная 65 кв.м. за 5 млн руб.
Хотите узнать подробнее?"
```

### Example 2: OOD Query ✅
```
Customer: "Вы продаете пиццу?"

Tool output:
⚠️ NO RELEVANT PRODUCTS FOUND

Your query 'пицца' did not match any products/services in our catalog.
The search found 3 result(s), but the best match had only 35.2% similarity (threshold: 70%).

This means we likely don't offer products/services related to 'пицца'.
Please inform the customer politely that this specific item/service is not available.

Agent response:
"Извините, но мы не продаем пиццу 😊
Мы специализируемся на недвижимости - квартирах, домах и коттеджах.
Могу помочь подобрать жилье?"
```

### Example 3: Ambiguous Query ⚠️
```
Customer: "Сколько стоит?"

Tool output:
✅ Found 5 relevant result(s) (filtered out 2 low-confidence)

[Multiple products with prices]

Agent response:
"У нас есть варианты в разных ценовых категориях!
Что именно вас интересует - квартиры, дома или консультация?
Цены начинаются от 3.5 млн руб. за студию."
```

## Troubleshooting

### Issue: Too many OOD results
**Symptom**: Relevant queries getting filtered

**Fix**:
```bash
# Lower threshold
export EMBEDDING_SIMILARITY_THRESHOLD=0.6

# Test again
python scripts/test_ood_detection.py
```

### Issue: Not enough filtering
**Symptom**: Irrelevant results still returned

**Fix**:
```bash
# Raise threshold
export EMBEDDING_SIMILARITY_THRESHOLD=0.8

# Test again
python scripts/test_ood_detection.py
```

### Issue: Empty results for everything
**Symptom**: All queries return "not found"

**Fix**:
```bash
# Check database
python scripts/verify_embedding_setup.py

# Populate if empty
python scripts/populate_embeddings.py
```

## Key Takeaways

1. ✅ **OOD filtering is automatic** - no manual configuration needed
2. ✅ **Agent gets clear signals** - "found" vs "not found"
3. ✅ **Threshold is tunable** - adjust via environment variable
4. ✅ **Quality is measurable** - confidence scores and tests
5. ✅ **Behavior is predictable** - consistent filtering at threshold

## Next Steps

1. **Verify Setup**:
   ```bash
   python scripts/verify_embedding_setup.py
   ```

2. **Populate Data**:
   ```bash
   python scripts/populate_embeddings.py
   ```

3. **Test OOD**:
   ```bash
   python scripts/test_ood_detection.py
   ```

4. **Monitor in Production**:
   - Check logs for OOD rate
   - Adjust threshold if needed
   - Add more products to reduce false negatives

## Conclusion

The OOD detection system ensures your agent provides **accurate, trustworthy responses** by:
- ✅ Filtering irrelevant results automatically
- ✅ Returning clear "not found" messages
- ✅ Preventing false information
- ✅ Maintaining customer trust

All managed through a simple 0.7 similarity threshold! 🎯
