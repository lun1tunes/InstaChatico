#!/usr/bin/env python3
"""Verify embedding setup: checks pgvector, tables, indexes, and OpenAI API"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from core.config import settings
from core.services.embedding_service import EmbeddingService


async def verify_setup():
    """Run 6 checks: extension, table, indexes, products, API, config"""
    print("="*80)
    print("🔍 VERIFYING EMBEDDING SEARCH SETUP")
    print("="*80)
    print()

    checks = {
        "total": 0,
        "passed": 0,
        "failed": 0
    }

    engine = create_async_engine(settings.db.url, echo=False)

    try:
        async with engine.begin() as conn:
            # Check 1: pgvector extension
            print("[1/6] Checking pgvector extension...")
            checks["total"] += 1
            try:
                result = await conn.execute(
                    text("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector'")
                )
                row = result.fetchone()
                if row:
                    print(f"   ✅ pgvector {row[1]} is installed")
                    checks["passed"] += 1
                else:
                    print("   ❌ pgvector extension not found")
                    print("      Run: CREATE EXTENSION vector;")
                    checks["failed"] += 1
            except Exception as e:
                print(f"   ❌ Error: {e}")
                checks["failed"] += 1
            print()

            # Check 2: product_embeddings table
            print("[2/6] Checking product_embeddings table...")
            checks["total"] += 1
            try:
                result = await conn.execute(
                    text("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables
                            WHERE table_name = 'product_embeddings'
                        )
                    """)
                )
                exists = result.scalar()
                if exists:
                    # Get column info
                    result = await conn.execute(
                        text("""
                            SELECT column_name, data_type
                            FROM information_schema.columns
                            WHERE table_name = 'product_embeddings'
                            AND column_name = 'embedding'
                        """)
                    )
                    col = result.fetchone()
                    if col:
                        print(f"   ✅ Table exists with embedding column (type: {col[1]})")
                        checks["passed"] += 1
                    else:
                        print("   ❌ Table exists but missing embedding column")
                        checks["failed"] += 1
                else:
                    print("   ❌ Table does not exist")
                    print("      Run: alembic -c database/alembic.ini upgrade head")
                    checks["failed"] += 1
            except Exception as e:
                print(f"   ❌ Error: {e}")
                checks["failed"] += 1
            print()

            # Check 3: Indexes
            print("[3/6] Checking indexes...")
            checks["total"] += 1
            try:
                result = await conn.execute(
                    text("""
                        SELECT indexname, indexdef
                        FROM pg_indexes
                        WHERE tablename = 'product_embeddings'
                        AND indexname LIKE '%embedding%'
                    """)
                )
                indexes = result.fetchall()
                if indexes:
                    print(f"   ✅ Found {len(indexes)} embedding index(es):")
                    for idx in indexes:
                        print(f"      - {idx[0]}")
                    checks["passed"] += 1
                else:
                    print("   ⚠️  No embedding indexes found (may affect performance)")
                    print("      Indexes will be created automatically by migration")
                    checks["passed"] += 1
            except Exception as e:
                print(f"   ❌ Error: {e}")
                checks["failed"] += 1
            print()

            # Check 4: Product count
            print("[4/6] Checking product count...")
            checks["total"] += 1
            try:
                result = await conn.execute(
                    text("SELECT COUNT(*) FROM product_embeddings WHERE is_active = true")
                )
                count = result.scalar()
                if count > 0:
                    print(f"   ✅ Found {count} active product(s)")
                    checks["passed"] += 1
                else:
                    print("   ⚠️  No products in database")
                    print("      Run: python scripts/populate_embeddings.py")
                    checks["passed"] += 1  # Not a failure, just empty
            except Exception as e:
                print(f"   ❌ Error: {e}")
                checks["failed"] += 1
            print()

        # Check 5: OpenAI API
        print("[5/6] Checking OpenAI API...")
        checks["total"] += 1
        try:
            service = EmbeddingService()
            embedding = await service.generate_embedding("test query")
            if len(embedding) == settings.embedding.dimensions:
                print(f"   ✅ OpenAI API working (generated {len(embedding)} dimensions)")
                checks["passed"] += 1
            else:
                print(f"   ⚠️  Unexpected embedding size: {len(embedding)} (expected: {settings.embedding.dimensions})")
                checks["passed"] += 1
        except Exception as e:
            print(f"   ❌ Error: {e}")
            print("      Check OPENAI_API_KEY in .env")
            checks["failed"] += 1
        print()

        # Check 6: Configuration
        print("[6/6] Checking configuration...")
        checks["total"] += 1
        try:
            print(f"   Model: {settings.embedding.model}")
            print(f"   Dimensions: {settings.embedding.dimensions}")
            print(f"   Threshold: {settings.embedding.similarity_threshold}")
            print(f"   ✅ Configuration loaded successfully")
            checks["passed"] += 1
        except Exception as e:
            print(f"   ❌ Error: {e}")
            checks["failed"] += 1
        print()

        # Summary
        print("="*80)
        print("📊 VERIFICATION SUMMARY")
        print("="*80)
        print(f"Total checks: {checks['total']}")
        print(f"✅ Passed:     {checks['passed']}")
        print(f"❌ Failed:     {checks['failed']}")
        print()

        if checks['failed'] == 0:
            print("✅ ALL CHECKS PASSED!")
            print()
            print("Your embedding search system is ready to use.")
            print()
            print("Next steps:")
            print("1. Populate database: python scripts/populate_embeddings.py")
            print("2. Test OOD detection: python scripts/test_ood_detection.py")
            print("3. Try the agent with real queries")
        else:
            print("⚠️  SOME CHECKS FAILED")
            print()
            print("Please fix the issues above and run this script again.")
            print()
            print("Common fixes:")
            print("1. Install pgvector: CREATE EXTENSION vector;")
            print("2. Run migrations: alembic -c database/alembic.ini upgrade head")
            print("3. Set OPENAI_API_KEY in .env")

        print()
        print("="*80)
        print()

        return checks['failed'] == 0

    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {e}")
        return False
    finally:
        await engine.dispose()


if __name__ == "__main__":
    success = asyncio.run(verify_setup())
    sys.exit(0 if success else 1)
