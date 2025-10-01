#!/usr/bin/env python3
"""Test OOD detection: verifies filtering of irrelevant results below threshold"""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from core.config import settings
from core.services.embedding_service import EmbeddingService


# Test cases with expected outcomes
TEST_CASES = [
    # High-confidence queries (should return results)
    {
        "query": "квартиры в центре",
        "expected_outcome": "HIGH_CONFIDENCE",
        "description": "Relevant query in Russian - should find apartments"
    },
    {
        "query": "недвижимость",
        "expected_outcome": "HIGH_CONFIDENCE",
        "description": "Generic real estate query - should find multiple results"
    },
    {
        "query": "консультация",
        "expected_outcome": "HIGH_CONFIDENCE",
        "description": "Service query - should find consultation services"
    },
    {
        "query": "apartments in city center",
        "expected_outcome": "HIGH_CONFIDENCE",
        "description": "Relevant query in English - should find apartments"
    },
    {
        "query": "дом с участком",
        "expected_outcome": "HIGH_CONFIDENCE",
        "description": "House with land - should find cottages"
    },
    {
        "query": "студия",
        "expected_outcome": "HIGH_CONFIDENCE",
        "description": "Studio apartment - should find studios"
    },
    {
        "query": "премиум жилье",
        "expected_outcome": "HIGH_CONFIDENCE",
        "description": "Premium housing - should find penthouses"
    },
    {
        "query": "ипотека",
        "expected_outcome": "HIGH_CONFIDENCE",
        "description": "Mortgage - should find mortgage consultation"
    },

    # Low-confidence queries (OOD - should NOT return results)
    {
        "query": "пицца",
        "expected_outcome": "OOD",
        "description": "Completely unrelated - pizza (should trigger OOD)"
    },
    {
        "query": "pizza delivery",
        "expected_outcome": "OOD",
        "description": "Completely unrelated - pizza in English (should trigger OOD)"
    },
    {
        "query": "автомобили",
        "expected_outcome": "OOD",
        "description": "Unrelated - cars (should trigger OOD)"
    },
    {
        "query": "ноутбуки и компьютеры",
        "expected_outcome": "OOD",
        "description": "Unrelated - laptops (should trigger OOD)"
    },
    {
        "query": "стрижка и маникюр",
        "expected_outcome": "OOD",
        "description": "Unrelated - beauty services (should trigger OOD)"
    },
    {
        "query": "football tickets",
        "expected_outcome": "OOD",
        "description": "Unrelated - sports tickets (should trigger OOD)"
    },
    {
        "query": "книги по программированию",
        "expected_outcome": "OOD",
        "description": "Unrelated - programming books (should trigger OOD)"
    },

    # Edge cases
    {
        "query": "цена",
        "expected_outcome": "UNCLEAR",
        "description": "Ambiguous - price (could match multiple things)"
    },
    {
        "query": "купить",
        "expected_outcome": "UNCLEAR",
        "description": "Ambiguous - buy (too generic)"
    },
]


async def test_ood_detection():
    """Test high-confidence vs OOD filtering with relevant and irrelevant queries"""
    print("="*80)
    print("🧪 TESTING OUT-OF-DISTRIBUTION (OOD) DETECTION")
    print("="*80)
    print()

    # Create database connection
    engine = create_async_engine(settings.db.url, echo=False)
    session_factory = async_sessionmaker(bind=engine, autoflush=False, autocommit=False)

    test_results = {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "unclear": 0
    }

    async with session_factory() as session:
        try:
            embedding_service = EmbeddingService()

            # Get threshold for display
            threshold = embedding_service.SIMILARITY_THRESHOLD
            print(f"📊 Similarity Threshold: {threshold} (70%)")
            print(f"   Results with similarity < {threshold} are filtered as OOD")
            print()
            print("="*80)
            print()

            for idx, test_case in enumerate(TEST_CASES, 1):
                query = test_case["query"]
                expected = test_case["expected_outcome"]
                description = test_case["description"]

                test_results["total"] += 1

                print(f"[Test {idx}/{len(TEST_CASES)}] {description}")
                print(f"   Query: '{query}'")
                print(f"   Expected: {expected}")

                try:
                    # Perform search
                    results = await embedding_service.search_similar_products(
                        query=query,
                        session=session,
                        limit=3
                    )

                    # Analyze results
                    if not results:
                        actual_outcome = "EMPTY_DB"
                        print(f"   ❌ Result: DATABASE EMPTY")
                    else:
                        high_confidence = [r for r in results if not r['is_ood']]
                        low_confidence = [r for r in results if r['is_ood']]

                        best_similarity = results[0]['similarity']

                        if high_confidence:
                            actual_outcome = "HIGH_CONFIDENCE"
                            print(f"   ✅ Result: HIGH CONFIDENCE")
                            print(f"      Found {len(high_confidence)} high-confidence result(s)")
                            print(f"      Best match: {results[0]['title']} (similarity: {best_similarity:.4f})")
                        else:
                            actual_outcome = "OOD"
                            print(f"   🚫 Result: OUT-OF-DISTRIBUTION (OOD)")
                            print(f"      All results filtered (best similarity: {best_similarity:.4f} < {threshold})")

                    # Check if result matches expectation
                    if expected == "UNCLEAR":
                        test_results["unclear"] += 1
                        print(f"   ⚠️  Status: UNCLEAR (ambiguous test case)")
                    elif actual_outcome == expected:
                        test_results["passed"] += 1
                        print(f"   ✅ Status: PASSED")
                    else:
                        test_results["failed"] += 1
                        print(f"   ❌ Status: FAILED (expected {expected}, got {actual_outcome})")

                    # Show top 3 results for debugging
                    if results:
                        print(f"      Top results:")
                        for i, result in enumerate(results[:3], 1):
                            ood_mark = " [OOD]" if result['is_ood'] else ""
                            print(f"        {i}. {result['title']} - {result['similarity']:.4f}{ood_mark}")

                except Exception as e:
                    test_results["failed"] += 1
                    print(f"   ❌ ERROR: {e}")

                print()
                print("-"*80)
                print()

            # Print summary
            print()
            print("="*80)
            print("📊 TEST SUMMARY")
            print("="*80)
            print(f"Total tests:     {test_results['total']}")
            print(f"✅ Passed:        {test_results['passed']}")
            print(f"❌ Failed:        {test_results['failed']}")
            print(f"⚠️  Unclear:       {test_results['unclear']}")
            print()

            pass_rate = (test_results['passed'] / (test_results['total'] - test_results['unclear'])) * 100 if (test_results['total'] - test_results['unclear']) > 0 else 0
            print(f"Pass Rate: {pass_rate:.1f}%")
            print()

            if test_results['failed'] == 0:
                print("✅ ALL TESTS PASSED! OOD detection is working correctly.")
            else:
                print("⚠️  SOME TESTS FAILED. Review the results above.")

            print()
            print("="*80)
            print()

            # Recommendations
            print("💡 RECOMMENDATIONS:")
            print()
            if test_results['failed'] > 0:
                print("1. Check if the database has enough diverse products")
                print("2. Consider adjusting SIMILARITY_THRESHOLD in embedding_service.py")
                print("   - Current: 0.7 (70%)")
                print("   - Increase (e.g., 0.8) for stricter filtering")
                print("   - Decrease (e.g., 0.6) for more lenient filtering")
                print()
                print("3. Add more products to cover edge cases:")
                print("   - Run: python scripts/populate_embeddings.py")
                print("   - Or add custom products for your business")
            else:
                print("✅ OOD detection is working correctly!")
                print("   - The system properly filters out irrelevant queries")
                print("   - High-confidence matches are returned for relevant queries")
                print("   - You can safely use the embedding_search tool in production")

            print()

        except Exception as e:
            print(f"\n❌ CRITICAL ERROR: {e}")
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(test_ood_detection())
