# Embedding Search System Documentation

## Overview

The embedding search system enables semantic search for products/services using OpenAI embeddings and PostgreSQL's pgvector extension. It includes automatic **out-of-distribution (OOD) detection** to filter irrelevant results.

## How It Works

### 1. Vector Embeddings
- **Model**: `text-embedding-3-small` (1536 dimensions)
- **Normalization**: All vectors are normalized by OpenAI
- **Similarity**: Cosine similarity (optimal for normalized vectors)

### 2. OOD Detection
The system automatically filters out irrelevant results using a similarity threshold:
- **Threshold**: 0.7 (70% similarity) by default
- **Behavior**: Results below threshold are marked as OOD and filtered
- **Result**: Agent receives only high-confidence matches or "not found" message

### 3. Search Flow
```
User Query → OpenAI Embedding → Cosine Similarity Search → OOD Filter → Results
                                         ↓
                              pgvector IVFFlat Index
                                         ↓
                              All matches retrieved
                                         ↓
                              Filter: similarity ≥ 0.7
                                         ↓
                     ┌──────────────────┴──────────────────┐
                     ↓                                      ↓
            High-Confidence Results                  OOD Results
            (returned to agent)                      (filtered out)
```

## Configuration

### Environment Variables

Add to your `.env` file:

```bash
# Embedding Search Settings (optional - defaults shown)
EMBEDDING_SIMILARITY_THRESHOLD=0.7    # OOD threshold (0.0-1.0)
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
```

### Threshold Tuning

| Threshold | Behavior | Use Case |
|-----------|----------|----------|
| 0.5-0.6 | Very lenient | Large catalog, accept fuzzy matches |
| **0.7** | **Balanced (default)** | **Most use cases** |
| 0.8-0.9 | Very strict | Small catalog, exact matches only |

**Rule of thumb**:
- Increase threshold if getting too many false positives
- Decrease threshold if missing relevant results

## Database Schema

### `product_embeddings` Table

```sql
CREATE TABLE product_embeddings (
    id SERIAL PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    description TEXT NOT NULL,
    category VARCHAR(100),
    price VARCHAR(100),
    embedding vector(1536) NOT NULL,  -- pgvector type
    tags TEXT,
    url VARCHAR(500),
    image_url VARCHAR(500),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- IVFFlat index for fast cosine similarity search
CREATE INDEX idx_product_embedding_cosine
ON product_embeddings
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
```

## Usage Examples

### 1. Populate Database

```bash
# Add sample products
cd /var/www/instachatico/app
python scripts/populate_embeddings.py
```

### 2. Test OOD Detection

```bash
# Run comprehensive tests
python scripts/test_ood_detection.py
```

Expected output:
```
[Test 1] Relevant query in Russian - should find apartments
   Query: 'квартиры в центре'
   Expected: HIGH_CONFIDENCE
   ✅ Result: HIGH CONFIDENCE
      Found 3 high-confidence result(s)
      Best match: Квартира в центре (similarity: 0.9234)
   ✅ Status: PASSED

[Test 9] Completely unrelated - pizza (should trigger OOD)
   Query: 'пицца'
   Expected: OOD
   🚫 Result: OUT-OF-DISTRIBUTION (OOD)
      All results filtered (best similarity: 0.3421 < 0.7)
   ✅ Status: PASSED
```

### 3. Agent Usage

The agent automatically uses `embedding_search` when customers ask about products:

**Scenario 1 - Relevant Query** (High Confidence)
```
Customer: "Какие у вас квартиры в центре?"
Agent: embedding_search(query="квартиры в центре")
Result: ✅ Found 3 relevant results (85-92% confidence)
Response: "У нас есть несколько вариантов квартир в центре! [details]"
```

**Scenario 2 - Irrelevant Query** (OOD)
```
Customer: "Вы продаете пиццу?"
Agent: embedding_search(query="пицца")
Result: ⚠️ NO RELEVANT PRODUCTS FOUND (best match: 35%)
Response: "Извините, мы не продаем пиццу. Мы специализируемся на недвижимости."
```

## API Reference

### EmbeddingService

```python
from core.services.embedding_service import EmbeddingService

service = EmbeddingService()

# Search for products
results = await service.search_similar_products(
    query="квартиры",
    session=session,
    limit=5,
    category_filter="Недвижимость",  # Optional
    include_inactive=False
)

# Add new product
product = await service.add_product(
    title="Новая квартира",
    description="Описание...",
    session=session,
    category="Недвижимость",
    price="5 000 000 руб."
)
```

### embedding_search Tool

```python
from core.agents.tools import embedding_search

# Used by OpenAI Agents SDK
result = await embedding_search(
    query="apartments",
    limit=5,
    category="Real Estate"  # Optional
)
```

## OOD Detection Details

### What is OOD?

**Out-of-Distribution (OOD)** detection identifies when a query is semantically different from all products in the database.

### Why It Matters

Without OOD detection:
- Customer asks: "Do you sell pizza?"
- System returns: "Penthouse apartment" (best match: 35%)
- Agent says: "Yes, we have pizza!" ❌ WRONG

With OOD detection:
- Customer asks: "Do you sell pizza?"
- System filters: All results < 70% threshold
- Agent says: "Sorry, we don't sell pizza" ✅ CORRECT

### How It Works

1. **Cosine Similarity Calculation**
   ```
   similarity = 1 - cosine_distance(query_embedding, product_embedding)
   ```

2. **OOD Classification**
   ```python
   is_ood = similarity < SIMILARITY_THRESHOLD  # < 0.7
   ```

3. **Filtering**
   ```python
   high_confidence = [r for r in results if not r['is_ood']]

   if not high_confidence:
       return "NO RELEVANT PRODUCTS FOUND"
   else:
       return high_confidence
   ```

### Similarity Scores Explained

| Score | Meaning | Example |
|-------|---------|---------|
| 0.90-1.00 | Excellent match | "квартиры" → "Квартира в центре" |
| 0.80-0.89 | Good match | "жилье" → "Апартаменты у моря" |
| **0.70-0.79** | **Acceptable match** | "недвижимость" → "Студия" |
| 0.60-0.69 | Weak match (OOD) | "помещение" → "Консультация" |
| < 0.60 | Poor match (OOD) | "пицца" → "Квартира" |

## Performance Optimization

### Index Configuration

```sql
-- IVFFlat parameters
WITH (lists = 100)  -- Number of clusters

-- Adjust based on dataset size:
-- Small (<1000 rows): lists = 50
-- Medium (1000-10000): lists = 100
-- Large (>10000): lists = sqrt(rows)
```

### Query Performance

- **Cold query**: ~50-100ms (first query after restart)
- **Warm query**: ~10-30ms (subsequent queries)
- **Index scan**: O(√n) instead of O(n) with IVFFlat

### Embedding Generation

- **Latency**: ~100-200ms per OpenAI API call
- **Caching**: Embeddings stored in database
- **Batch operations**: Generate embeddings during data import

## Troubleshooting

### Issue: All queries return OOD

**Cause**: Threshold too high or empty database

**Solution**:
```bash
# Check database
python scripts/test_ood_detection.py

# Lower threshold
export EMBEDDING_SIMILARITY_THRESHOLD=0.6

# Add more products
python scripts/populate_embeddings.py
```

### Issue: Getting irrelevant results

**Cause**: Threshold too low

**Solution**:
```bash
# Increase threshold
export EMBEDDING_SIMILARITY_THRESHOLD=0.8
```

### Issue: pgvector extension not found

**Cause**: Extension not installed

**Solution**:
```bash
# In database container
docker exec -it postgres psql -U lun1z -d instagram_db
CREATE EXTENSION vector;

# Or re-run init.sql
docker exec -i postgres psql -U lun1z -d instagram_db < database/init.sql
```

## Migration Steps

### 1. Install Dependencies
```bash
poetry install
```

### 2. Run Migration
```bash
alembic -c database/alembic.ini upgrade head
```

### 3. Verify Extension
```bash
docker exec -it postgres psql -U lun1z -d instagram_db -c "\dx"
```

Expected output:
```
   Name    | Version
-----------+---------
 pgvector  | 0.5.0
 uuid-ossp | 1.1
```

### 4. Populate Data
```bash
python scripts/populate_embeddings.py
```

### 5. Test
```bash
python scripts/test_ood_detection.py
```

## Best Practices

### 1. Product Descriptions
- **Be specific**: "Двухкомнатная квартира 65 кв.м." > "Квартира"
- **Include details**: Location, features, price range
- **Use natural language**: Write for humans, not keywords
- **Multilingual**: Use the language your customers speak

### 2. Data Management
- **Regular updates**: Keep product catalog current
- **Deactivate old products**: Set `is_active=false` instead of deleting
- **Regenerate embeddings**: After description changes
- **Monitor similarity scores**: Adjust threshold as needed

### 3. Testing
- **Test with real queries**: Use actual customer questions
- **Track OOD rate**: High rate may indicate catalog gaps
- **A/B test threshold**: Find optimal value for your use case
- **Monitor agent responses**: Ensure quality with new products

## Advanced Topics

### Custom Embedding Models

```bash
# Use larger model for better accuracy
export EMBEDDING_MODEL=text-embedding-3-large
export EMBEDDING_DIMENSIONS=3072

# Update database schema accordingly
alembic revision --autogenerate -m "update embedding dimensions"
```

### Category-Specific Search

```python
# Search only in specific category
results = await service.search_similar_products(
    query="консультация",
    session=session,
    category_filter="Услуги"
)
```

### Batch Import

```python
# Efficient batch import
products = [...]  # List of product dicts

for product in products:
    await service.add_product(**product)

await session.commit()  # Single commit
```

## Security Considerations

- ✅ All queries are logged for monitoring
- ✅ No SQL injection (parameterized queries)
- ✅ Rate limiting via OpenAI API keys
- ✅ Access control via database permissions

## Support

For issues or questions:
1. Check logs: `docker-compose logs -f`
2. Run diagnostics: `python scripts/test_ood_detection.py`
3. Review this documentation
4. Check OpenAI API status
