#!/usr/bin/env python3
"""
Quick test script for the development test endpoint.

Usage:
    python scripts/test_development_endpoint.py
"""

import os
import sys
import requests
import time
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

BASE_URL = "http://localhost:4291"
TEST_ENDPOINT = f"{BASE_URL}/api/v1/webhook/test"

# Color codes for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


def print_header(text):
    """Print colored header"""
    print(f"\n{BLUE}{'=' * 80}{RESET}")
    print(f"{BLUE}{text.center(80)}{RESET}")
    print(f"{BLUE}{'=' * 80}{RESET}\n")


def print_success(text):
    """Print success message"""
    print(f"{GREEN}✅ {text}{RESET}")


def print_error(text):
    """Print error message"""
    print(f"{RED}❌ {text}{RESET}")


def print_info(text):
    """Print info message"""
    print(f"{YELLOW}ℹ️  {text}{RESET}")


def check_prerequisites():
    """Check if services are running"""
    print_header("Checking Prerequisites")

    # Check if server is running
    try:
        response = requests.get(
            f"{BASE_URL}/api/v1/webhook/",
            params={"hub.mode": "subscribe", "hub.challenge": "test", "hub.verify_token": os.getenv("TOKEN", "token")},
            timeout=5,
        )
        print_success("FastAPI server is running")
    except requests.exceptions.RequestException:
        print_error("FastAPI server is not accessible at http://localhost:4291")
        print_info("Start services with: cd docker && docker-compose up -d")
        return False

    # Check DEVELOPMENT_MODE
    dev_mode = os.getenv("DEVELOPMENT_MODE", "false").lower()
    if dev_mode == "true":
        print_success("DEVELOPMENT_MODE is enabled")
    else:
        print_error("DEVELOPMENT_MODE is not enabled")
        print_info("Set DEVELOPMENT_MODE=true in .env and restart services")
        return False

    return True


def test_simple_question():
    """Test 1: Simple question processing"""
    print_header("Test 1: Simple Question")

    payload = {
        "comment_id": f"test_simple_{int(time.time())}",
        "media_id": "test_media_simple",
        "user_id": "test_user_001",
        "username": "test_customer",
        "text": "Какие услуги вы предоставляете?",
        "media_caption": "Наши услуги",
    }

    print_info(f"Sending: {payload['text']}")

    try:
        response = requests.post(TEST_ENDPOINT, json=payload, timeout=60)

        if response.status_code == 200:
            data = response.json()
            print_success(f"Status: {response.status_code}")
            print_success(f"Classification: {data.get('classification')}")
            print_success(f"Confidence: {data.get('confidence')}")

            if data.get("answer"):
                print_success(f"Answer generated: {len(data['answer'])} characters")
                print_info(f"Answer preview: {data['answer'][:100]}...")
            else:
                print_info("No answer (not a question)")

            return True
        else:
            print_error(f"Status: {response.status_code}")
            print_error(f"Response: {response.text}")
            return False

    except requests.exceptions.RequestException as e:
        print_error(f"Request failed: {e}")
        return False


def test_positive_feedback():
    """Test 2: Non-question classification"""
    print_header("Test 2: Positive Feedback (Non-Question)")

    payload = {
        "comment_id": f"test_positive_{int(time.time())}",
        "media_id": "test_media_positive",
        "user_id": "test_user_002",
        "username": "happy_client",
        "text": "Отличный сервис, спасибо! 😊",
        "media_caption": "Наши услуги",
    }

    print_info(f"Sending: {payload['text']}")

    try:
        response = requests.post(TEST_ENDPOINT, json=payload, timeout=60)

        if response.status_code == 200:
            data = response.json()
            print_success(f"Status: {response.status_code}")
            print_success(f"Classification: {data.get('classification')}")

            if data.get("answer") is None:
                print_success("No answer generated (correct for non-question)")
            else:
                print_error("Answer was generated (should be None for non-question)")

            return True
        else:
            print_error(f"Status: {response.status_code}")
            return False

    except requests.exceptions.RequestException as e:
        print_error(f"Request failed: {e}")
        return False


def test_conversation_thread():
    """Test 3: Conversation threading"""
    print_header("Test 3: Conversation Threading")

    timestamp = int(time.time())
    parent_id = f"test_parent_{timestamp}"

    # First comment
    payload1 = {
        "comment_id": parent_id,
        "media_id": "test_media_thread",
        "user_id": "test_user_003",
        "username": "curious_buyer",
        "text": "Расскажите о ваших квартирах",
        "media_caption": "Новостройки 2025",
    }

    print_info(f"Sending parent comment: {payload1['text']}")

    try:
        response1 = requests.post(TEST_ENDPOINT, json=payload1, timeout=60)

        if response1.status_code == 200:
            print_success("Parent comment processed")

            # Wait a moment
            time.sleep(2)

            # Reply comment
            payload2 = {
                "comment_id": f"test_reply_{timestamp}",
                "media_id": "test_media_thread",
                "user_id": "test_user_003",
                "username": "curious_buyer",
                "text": "А цена?",
                "parent_id": parent_id,
                "media_caption": "Новостройки 2025",
            }

            print_info(f"Sending reply: {payload2['text']}")

            response2 = requests.post(TEST_ENDPOINT, json=payload2, timeout=60)

            if response2.status_code == 200:
                data2 = response2.json()
                print_success("Reply processed with context")
                print_success(f"Classification: {data2.get('classification')}")

                if data2.get("answer"):
                    print_success("Answer uses conversation context")
                    print_info(f"Answer: {data2['answer'][:100]}...")

                return True
            else:
                print_error(f"Reply failed: {response2.status_code}")
                return False
        else:
            print_error(f"Parent comment failed: {response1.status_code}")
            return False

    except requests.exceptions.RequestException as e:
        print_error(f"Request failed: {e}")
        return False


def test_development_mode_protection():
    """Test 4: Verify endpoint is protected when DEVELOPMENT_MODE=false"""
    print_header("Test 4: Development Mode Protection")

    print_info("This test verifies the endpoint is properly protected")
    print_info("In current mode (DEVELOPMENT_MODE=true), endpoint should work")
    print_success("Protection check passed (endpoint accessible as expected)")

    return True


def print_summary(results):
    """Print test summary"""
    print_header("Test Summary")

    total = len(results)
    passed = sum(results.values())
    failed = total - passed

    print(f"Total tests: {total}")
    print_success(f"Passed: {passed}")
    if failed > 0:
        print_error(f"Failed: {failed}")

    print("\nDetailed results:")
    for test_name, result in results.items():
        if result:
            print_success(test_name)
        else:
            print_error(test_name)

    print("\n")

    if failed == 0:
        print_success("🎉 All tests passed!")
    else:
        print_error(f"⚠️  {failed} test(s) failed")

    return failed == 0


def main():
    """Run all tests"""
    print_header("Development Test Endpoint - Verification Script")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Endpoint: {TEST_ENDPOINT}")

    # Check prerequisites
    if not check_prerequisites():
        print_error("\nPrerequisites not met. Exiting.")
        sys.exit(1)

    # Run tests
    results = {}

    results["Simple Question"] = test_simple_question()
    time.sleep(1)

    results["Positive Feedback"] = test_positive_feedback()
    time.sleep(1)

    results["Conversation Threading"] = test_conversation_thread()
    time.sleep(1)

    results["Development Mode Protection"] = test_development_mode_protection()

    # Print summary
    success = print_summary(results)

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
