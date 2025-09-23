#!/bin/bash

# Instagram Environment Setup Script

echo "🔧 Instagram Environment Setup"
echo "=============================="

# Check if INSTA_TOKEN is set
if [ -z "$INSTA_TOKEN" ]; then
    echo "❌ INSTA_TOKEN environment variable is not set"
    echo ""
    echo "To set it, run:"
    echo "export INSTA_TOKEN=\"your_instagram_access_token\""
    echo ""
    echo "Or add it to your .env file:"
    echo "INSTA_TOKEN=your_instagram_access_token"
    echo ""
    echo "Then restart the services:"
    echo "docker-compose up -d api celery_worker"
    exit 1
fi

echo "✅ INSTA_TOKEN is set: ${INSTA_TOKEN:0:10}...${INSTA_TOKEN: -4}"

# Check if services are running
echo ""
echo "🔍 Checking services..."

if docker-compose ps | grep -q "instagram_api.*Up"; then
    echo "✅ API service is running"
else
    echo "❌ API service is not running"
    echo "Run: docker-compose up -d api"
fi

if docker-compose ps | grep -q "instagram_celery_worker.*Up"; then
    echo "✅ Celery worker is running"
else
    echo "❌ Celery worker is not running"
    echo "Run: docker-compose up -d celery_worker"
fi

# Test token validation
echo ""
echo "🧪 Testing token validation..."
response=$(curl -s "http://localhost:4291/api/v1/instagram-replies/validate-token")

if echo "$response" | grep -q '"status":"success"'; then
    echo "✅ Token validation: PASSED"
    echo "$response" | jq '.'
else
    echo "❌ Token validation: FAILED"
    echo "$response" | jq '.'
fi

# Test page info
echo ""
echo "🧪 Testing page info..."
response=$(curl -s "http://localhost:4291/api/v1/instagram-replies/page-info")

if echo "$response" | grep -q '"status":"success"'; then
    echo "✅ Page info: PASSED"
    echo "$response" | jq '.'
else
    echo "❌ Page info: FAILED"
    echo "$response" | jq '.'
fi

echo ""
echo "📝 Next steps:"
echo "1. If token validation failed, generate a new Instagram access token"
echo "2. Make sure the token has required permissions:"
echo "   - instagram_basic"
echo "   - instagram_manage_comments"
echo "   - pages_show_list"
echo "   - page_read_engagement"
echo "3. Update INSTA_TOKEN environment variable"
echo "4. Restart services: docker-compose up -d api celery_worker"
