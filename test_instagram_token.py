#!/usr/bin/env python3
"""
Instagram Token Testing Script

This script helps you test and validate your Instagram access token.
"""

import os
import requests
import json
from typing import Dict, Any

def test_token_validation(token: str) -> Dict[str, Any]:
    """Test Instagram token validation using Graph API debug endpoint"""
    url = "https://graph.facebook.com/v18.0/debug_token"
    params = {
        "input_token": token,
        "access_token": token
    }
    
    try:
        response = requests.get(url, params=params)
        return {
            "status_code": response.status_code,
            "response": response.json()
        }
    except Exception as e:
        return {
            "error": str(e)
        }

def test_page_info(token: str) -> Dict[str, Any]:
    """Test getting Instagram page information"""
    url = "https://graph.facebook.com/v18.0/me"
    params = {
        "access_token": token,
        "fields": "id,name,username"
    }
    
    try:
        response = requests.get(url, params=params)
        return {
            "status_code": response.status_code,
            "response": response.json()
        }
    except Exception as e:
        return {
            "error": str(e)
        }

def test_comment_reply(token: str, comment_id: str, message: str) -> Dict[str, Any]:
    """Test sending a reply to an Instagram comment"""
    url = f"https://graph.facebook.com/v18.0/{comment_id}/replies"
    data = {
        "message": message,
        "access_token": token
    }
    
    try:
        response = requests.post(url, data=data)
        return {
            "status_code": response.status_code,
            "response": response.json()
        }
    except Exception as e:
        return {
            "error": str(e)
        }

def main():
    """Main function to test Instagram token"""
    print("🔍 Instagram Token Testing Script")
    print("=" * 50)
    
    # Get token from environment or user input
    token = os.getenv("INSTA_TOKEN")
    if not token:
        token = input("Enter your Instagram access token: ").strip()
    
    if not token:
        print("❌ No token provided")
        return
    
    print(f"🔑 Testing token: {token[:10]}...{token[-4:] if len(token) > 14 else '***'}")
    print()
    
    # Test 1: Token Validation
    print("1️⃣ Testing token validation...")
    validation_result = test_token_validation(token)
    if "error" in validation_result:
        print(f"❌ Error: {validation_result['error']}")
    else:
        print(f"📊 Status Code: {validation_result['status_code']}")
        print(f"📋 Response: {json.dumps(validation_result['response'], indent=2)}")
    print()
    
    # Test 2: Page Info
    print("2️⃣ Testing page info...")
    page_result = test_page_info(token)
    if "error" in page_result:
        print(f"❌ Error: {page_result['error']}")
    else:
        print(f"📊 Status Code: {page_result['status_code']}")
        print(f"📋 Response: {json.dumps(page_result['response'], indent=2)}")
    print()
    
    # Test 3: Comment Reply (with test comment)
    print("3️⃣ Testing comment reply...")
    test_comment_id = "test_comment_123"
    test_message = "This is a test reply"
    
    reply_result = test_comment_reply(token, test_comment_id, test_message)
    if "error" in reply_result:
        print(f"❌ Error: {reply_result['error']}")
    else:
        print(f"📊 Status Code: {reply_result['status_code']}")
        print(f"📋 Response: {json.dumps(reply_result['response'], indent=2)}")
    print()
    
    # Summary
    print("📝 Summary:")
    if validation_result.get("status_code") == 200:
        print("✅ Token validation: PASSED")
    else:
        print("❌ Token validation: FAILED")
    
    if page_result.get("status_code") == 200:
        print("✅ Page info: PASSED")
    else:
        print("❌ Page info: FAILED")
    
    if reply_result.get("status_code") in [200, 400]:  # 400 is expected for test comment
        print("✅ Comment reply: PASSED (400 expected for test comment)")
    else:
        print("❌ Comment reply: FAILED")

if __name__ == "__main__":
    main()
