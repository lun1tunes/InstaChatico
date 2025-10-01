#!/usr/bin/env python3
"""
Verify test data structure and content without database access.
This script checks if the test data is properly formatted.
"""

import sys
import os

# Add test_data to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from test_data.personal_care_products import PERSONAL_CARE_PRODUCTS, MEDIA_TEST_DATA

# Color codes
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


def print_success(text):
    print(f"{GREEN}✅ {text}{RESET}")


def print_error(text):
    print(f"{RED}❌ {text}{RESET}")


def print_info(text):
    print(f"{YELLOW}ℹ️  {text}{RESET}")


def print_header(text):
    print(f"\n{BLUE}{'=' * 80}{RESET}")
    print(f"{BLUE}{text.center(80)}{RESET}")
    print(f"{BLUE}{'=' * 80}{RESET}\n")


def verify_products():
    """Verify product data structure"""
    print_header("Verifying Products")

    required_fields = ["title", "description", "category", "price"]
    optional_fields = ["tags", "url", "image_url"]

    errors = 0
    warnings = 0

    for idx, product in enumerate(PERSONAL_CARE_PRODUCTS, 1):
        # Check required fields
        missing_fields = [f for f in required_fields if f not in product]
        if missing_fields:
            print_error(f"Product {idx}: Missing required fields: {missing_fields}")
            print_info(f"  Title: {product.get('title', 'N/A')[:50]}")
            errors += 1
            continue

        # Check optional fields
        missing_optional = [f for f in optional_fields if f not in product or not product[f]]
        if missing_optional:
            warnings += 1

        # Validate field types
        if not isinstance(product["title"], str) or len(product["title"]) == 0:
            print_error(f"Product {idx}: Invalid title")
            errors += 1

        if not isinstance(product["description"], str) or len(product["description"]) < 10:
            print_error(f"Product {idx}: Description too short")
            errors += 1

    print(f"\nTotal products: {len(PERSONAL_CARE_PRODUCTS)}")

    if errors == 0:
        print_success(f"All {len(PERSONAL_CARE_PRODUCTS)} products are valid!")
    else:
        print_error(f"Found {errors} error(s)")

    if warnings > 0:
        print_info(f"{warnings} products missing optional fields (this is OK)")

    return errors


def verify_media():
    """Verify media data structure"""
    print_header("Verifying Media")

    required_fields = ["id", "permalink", "caption", "media_type", "username"]

    errors = 0

    for idx, media in enumerate(MEDIA_TEST_DATA, 1):
        # Check required fields
        missing_fields = [f for f in required_fields if f not in media]
        if missing_fields:
            print_error(f"Media {idx}: Missing required fields: {missing_fields}")
            print_info(f"  ID: {media.get('id', 'N/A')}")
            errors += 1
            continue

        # Check ID prefix
        if not media["id"].startswith("test_"):
            print_error(f"Media {idx}: ID should start with 'test_' (got: {media['id']})")
            errors += 1

        # Validate media type
        valid_types = ["IMAGE", "VIDEO", "CAROUSEL_ALBUM"]
        if media["media_type"] not in valid_types:
            print_error(f"Media {idx}: Invalid media_type '{media['media_type']}' (must be one of {valid_types})")
            errors += 1

    print(f"\nTotal media: {len(MEDIA_TEST_DATA)}")

    if errors == 0:
        print_success(f"All {len(MEDIA_TEST_DATA)} media records are valid!")
    else:
        print_error(f"Found {errors} error(s)")

    return errors


def show_summary():
    """Show data summary"""
    print_header("Data Summary")

    # Count products by category
    categories = {}
    for product in PERSONAL_CARE_PRODUCTS:
        cat = product.get("category", "Unknown")
        categories[cat] = categories.get(cat, 0) + 1

    print("Products by category:")
    for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
        print(f"  {cat}: {count}")

    print(f"\nTotal products: {len(PERSONAL_CARE_PRODUCTS)}")
    print(f"Total media: {len(MEDIA_TEST_DATA)}")

    # Price range
    prices = []
    for product in PERSONAL_CARE_PRODUCTS:
        price_str = product.get("price", "0")
        # Extract numbers from price string
        price_num = "".join(c for c in price_str if c.isdigit())
        if price_num:
            prices.append(int(price_num))

    if prices:
        print(f"\nPrice range: {min(prices):,} ₽ - {max(prices):,} ₽")


def main():
    print_header("Test Data Verification")

    product_errors = verify_products()
    media_errors = verify_media()
    show_summary()

    print_header("Result")

    total_errors = product_errors + media_errors

    if total_errors == 0:
        print_success("✨ All test data is valid and ready to use! ✨")
        print("\nNext steps:")
        print("  1. Start Docker services: cd docker && docker-compose up -d")
        print("  2. Load test data: python scripts/load_test_data.py")
        print("  3. Test endpoint: curl -X POST http://localhost:4291/api/v1/webhook/test ...")
        return 0
    else:
        print_error(f"Found {total_errors} error(s) in test data")
        print_info("Please fix the errors before loading data")
        return 1


if __name__ == "__main__":
    sys.exit(main())
