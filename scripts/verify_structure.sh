#!/bin/bash
# Verification script to check project structure after reorganization

set -e

echo "============================================================"
echo "  InstaChatico - Structure Verification Script"
echo "============================================================"
echo

PROJECT_ROOT="/var/www/instachatico/app"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

success_count=0
fail_count=0

check_exists() {
    local path=$1
    local description=$2
    
    if [ -e "$path" ]; then
        echo -e "${GREEN}✓${NC} $description: $path"
        ((success_count++))
        return 0
    else
        echo -e "${RED}✗${NC} $description: $path (NOT FOUND)"
        ((fail_count++))
        return 1
    fi
}

echo "1. Checking directory structure..."
echo "-----------------------------------------------------------"
check_exists "$PROJECT_ROOT/src" "Source directory"
check_exists "$PROJECT_ROOT/database" "Database directory"
check_exists "$PROJECT_ROOT/scripts" "Scripts directory"
check_exists "$PROJECT_ROOT/docker" "Docker directory"
echo

echo "2. Checking source files..."
echo "-----------------------------------------------------------"
check_exists "$PROJECT_ROOT/src/main.py" "Main application"
check_exists "$PROJECT_ROOT/src/celery_worker.py" "Celery worker"
check_exists "$PROJECT_ROOT/src/api_v1" "API v1 package"
check_exists "$PROJECT_ROOT/src/core" "Core package"
check_exists "$PROJECT_ROOT/src/conversations" "Conversations directory"
echo

echo "3. Checking database files..."
echo "-----------------------------------------------------------"
check_exists "$PROJECT_ROOT/database/alembic.ini" "Alembic config"
check_exists "$PROJECT_ROOT/database/migrations" "Migrations directory"
check_exists "$PROJECT_ROOT/database/migrations/env.py" "Migration environment"
check_exists "$PROJECT_ROOT/database/init.sql" "Database init script"
echo

echo "4. Checking Docker files..."
echo "-----------------------------------------------------------"
check_exists "$PROJECT_ROOT/docker/docker-compose.yml" "Docker Compose"
check_exists "$PROJECT_ROOT/docker/Dockerfile" "Dockerfile"
check_exists "$PROJECT_ROOT/docker/config/redis" "Redis config"
check_exists "$PROJECT_ROOT/docker/config/dozzle" "Dozzle config"
echo

echo "5. Checking configuration files..."
echo "-----------------------------------------------------------"
check_exists "$PROJECT_ROOT/pyproject.toml" "Poetry config"
check_exists "$PROJECT_ROOT/.gitignore" "Git ignore"
check_exists "$PROJECT_ROOT/README.md" "README"
check_exists "$PROJECT_ROOT/QUICKSTART.md" "Quick start guide"
check_exists "$PROJECT_ROOT/MIGRATION_GUIDE.md" "Migration guide"
echo

echo "6. Checking for old files that should be removed..."
echo "-----------------------------------------------------------"
if [ -e "$PROJECT_ROOT/alembic" ]; then
    echo -e "${YELLOW}⚠${NC} Old alembic directory still exists (should be removed)"
    ((fail_count++))
else
    echo -e "${GREEN}✓${NC} Old alembic directory removed"
    ((success_count++))
fi

if [ -e "$PROJECT_ROOT/docker-compose.yml" ]; then
    echo -e "${YELLOW}⚠${NC} Old docker-compose.yml still exists (should be in docker/)"
    ((fail_count++))
else
    echo -e "${GREEN}✓${NC} Old docker-compose.yml removed from root"
    ((success_count++))
fi

if [ -e "$PROJECT_ROOT/Dockerfile" ]; then
    echo -e "${YELLOW}⚠${NC} Old Dockerfile still exists (should be in docker/)"
    ((fail_count++))
else
    echo -e "${GREEN}✓${NC} Old Dockerfile removed from root"
    ((success_count++))
fi
echo

echo "7. Testing Python imports (if in container/venv)..."
echo "-----------------------------------------------------------"
if command -v python &> /dev/null; then
    cd "$PROJECT_ROOT/src"
    if python test_imports.py 2>&1; then
        echo -e "${GREEN}✓${NC} Python imports test passed"
        ((success_count++))
    else
        echo -e "${RED}✗${NC} Python imports test failed"
        ((fail_count++))
    fi
else
    echo -e "${YELLOW}⚠${NC} Python not found in PATH, skipping import test"
fi
echo

echo "============================================================"
echo "  Verification Summary"
echo "============================================================"
echo -e "Passed: ${GREEN}$success_count${NC}"
echo -e "Failed: ${RED}$fail_count${NC}"
echo

if [ $fail_count -eq 0 ]; then
    echo -e "${GREEN}✅ ALL CHECKS PASSED!${NC}"
    echo "Your project structure is correctly organized."
    exit 0
else
    echo -e "${YELLOW}⚠ SOME CHECKS FAILED${NC}"
    echo "Please review the failed items above."
    exit 1
fi

