#!/bin/bash

# Instagram Worker User Setup Script
# This script sets up a dedicated user for running Instagram worker processes
# instead of using the root user for better security

set -e

echo "🔧 Setting up Instagram Worker User..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ This script must be run as root (use sudo)"
    exit 1
fi

# Create the worker user if it doesn't exist
if ! id "instagram-worker" &>/dev/null; then
    echo "👤 Creating instagram-worker user..."
    useradd -r -s /bin/bash -d /var/www/instachatico -m instagram-worker
    echo "✅ User created successfully"
else
    echo "ℹ️  User instagram-worker already exists"
fi

# Add user to docker group for container access
echo "🐳 Adding user to docker group..."
usermod -aG docker instagram-worker
echo "✅ User added to docker group"

# Set up directory permissions
echo "📁 Setting up directory permissions..."
chown -R instagram-worker:instagram-worker /var/www/instachatico/app
chmod -R 755 /var/www/instachatico/app
find /var/www/instachatico/app -type f -exec chmod 644 {} \;
chmod +x /var/www/instachatico/app/celery_worker.py

# Create conversations directory with proper permissions
mkdir -p /var/www/instachatico/app/conversations
chown -R instagram-worker:instagram-worker /var/www/instachatico/app/conversations
chmod 755 /var/www/instachatico/app/conversations

echo "✅ Directory permissions set"

# Test basic operations
echo "🧪 Testing user permissions..."
sudo -u instagram-worker ls -la /var/www/instachatico/app/conversations > /dev/null
echo "✅ Directory access test passed"

sudo -u instagram-worker python3 -c "import os; os.makedirs('/var/www/instachatico/app/conversations/test', exist_ok=True)" > /dev/null
sudo -u instagram-worker python3 -c "import sqlite3; conn = sqlite3.connect('/var/www/instachatico/app/conversations/test.db'); conn.close()" > /dev/null
echo "✅ File creation tests passed"

# Clean up test files
rm -rf /var/www/instachatico/app/conversations/test /var/www/instachatico/app/conversations/test.db

echo ""
echo "🎉 Instagram Worker User Setup Complete!"
echo ""
echo "📋 Summary:"
echo "   • User: instagram-worker"
echo "   • Home directory: /var/www/instachatico"
echo "   • Groups: instagram-worker, docker"
echo "   • App directory: /var/www/instachatico/app (owned by instagram-worker)"
echo "   • Conversations directory: /var/www/instachatico/app/conversations"
echo ""
echo "🚀 Next steps:"
echo "   1. Rebuild your Docker containers: docker-compose build"
echo "   2. Restart your services: docker-compose up -d"
echo "   3. Verify containers are running with the new user: docker-compose ps"
echo ""
echo "🔒 Security improvements:"
echo "   • Containers now run as non-root user (instagram-worker)"
echo "   • Added security_opt: no-new-privileges to prevent privilege escalation"
echo "   • Proper file permissions set for application directories"
echo ""
echo "⚠️  Note: The containers will automatically use the instagram-worker user"
echo "   as specified in the updated Dockerfile."
