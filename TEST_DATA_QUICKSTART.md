# Test Data - Quick Reference

## One-Time Setup

```bash
# Load 35 personal care products + 5 test media
python scripts/load_test_data.py
```

## Daily Use

```bash
# Clean test comments (after testing)
python scripts/clean_test_data.py --comments-only --confirm
```

## Commands Cheat Sheet

| Action | Command |
|--------|---------|
| **Load all test data** | `python scripts/load_test_data.py` |
| **Load + clean old** | `python scripts/load_test_data.py --clean` |
| **Only products** | `python scripts/load_test_data.py --products-only` |
| **Only media** | `python scripts/load_test_data.py --media-only` |
| **Clean all (confirm)** | `python scripts/clean_test_data.py` |
| **Clean all (no prompt)** | `python scripts/clean_test_data.py --confirm` |
| **Clean products only** | `python scripts/clean_test_data.py --products-only --confirm` |
| **Clean media only** | `python scripts/clean_test_data.py --media-only --confirm` |
| **Clean comments only** | `python scripts/clean_test_data.py --comments-only --confirm` |

## Test Data Includes

### Products (35 items)
- **Face Care**: Cleansers, creams, serums (Vitamin C, Hyaluronic, Niacinamide)
- **Masks**: Clay, sheet, alginate masks
- **Eye Care**: Eye creams, patches
- **Hair Care**: Shampoos, conditioners, masks, growth serums
- **Body Care**: Lotions, scrubs, hand creams, body oils
- **Sun Protection**: SPF creams, after-sun sprays
- **Sets**: Anti-age sets, travel kits, gift sets
- **Lip & Nail Care**: Lip balms, scrubs, nail serums

### Test Media (5 posts)
- `test_media_skincare_001` - Skincare post (Vitamin C serum)
- `test_media_hair_001` - Hair care products
- `test_media_promotion_001` - Promotion with discount
- `test_media_body_care_001` - Body care products
- `test_media_routine_001` - Evening skincare routine

## Quick Test

```bash
# 1. Load data
python scripts/load_test_data.py

# 2. Test endpoint
curl -X POST http://localhost:4291/api/v1/webhook/test \
  -H "Content-Type: application/json" \
  -d '{
    "comment_id": "test_quick_001",
    "media_id": "test_media_skincare_001",
    "user_id": "user_001",
    "username": "customer",
    "text": "Какие сыворотки для лица у вас есть?"
  }'

# Expected: Agent finds 3 serums (Vitamin C, Hyaluronic, Niacinamide)
```

## Test Queries Examples

| Query | Expected Products Found |
|-------|------------------------|
| "сыворотки для лица" | Vitamin C, Hyaluronic, Niacinamide serums |
| "крем для сухой кожи" | Shea hand cream, Moisturizing creams |
| "средства от морщин" | Retinol night cream, Anti-age sets |
| "маска для волос" | Coconut hair mask |
| "скраб для тела" | Coffee scrub |
| "солнцезащита" | SPF 50 face cream |
| "набор в подарок" | SPA gift set, Anti-age set |
| "пицца" 🍕 | NO PRODUCTS FOUND (OOD detection) |

## Database Check

```bash
# Check products loaded
docker exec postgres psql -U lun1z -d instagram_db -c \
  "SELECT COUNT(*) as products FROM product_embeddings;"

# Check test media
docker exec postgres psql -U lun1z -d instagram_db -c \
  "SELECT COUNT(*) as media FROM media WHERE id LIKE 'test_%';"

# Check test comments
docker exec postgres psql -U lun1z -d instagram_db -c \
  "SELECT COUNT(*) as comments FROM instagram_comments WHERE id LIKE 'test_%';"
```

## File Locations

```
scripts/
├── test_data/
│   └── personal_care_products.py    # 📝 Edit to add products
├── load_test_data.py                # 🚀 Load data
└── clean_test_data.py               # 🧹 Clean data

docs/
└── TEST_DATA_MANAGEMENT.md          # 📚 Full documentation
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Products not found | `python scripts/load_test_data.py --clean` |
| Permission denied | `chmod +x scripts/*.py` |
| DB connection error | `docker-compose ps postgres` |
| Too many test comments | `python scripts/clean_test_data.py --comments-only --confirm` |

## Before Production

```bash
# Remove ALL test data
python scripts/clean_test_data.py --confirm

# Verify clean
python scripts/clean_test_data.py
# Should show: "No test data found. Database is clean! ✨"
```

---

**Need more details?** See `docs/TEST_DATA_MANAGEMENT.md`

**Test endpoint?** See `docs/DEVELOPMENT_MODE_TESTING.md`

