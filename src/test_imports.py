#!/usr/bin/env python3
"""
Test script to verify all imports work correctly after restructure
"""
import sys
from pathlib import Path

# Add src to path (should already be there, but just in case)
sys.path.insert(0, str(Path(__file__).parent))


def test_imports():
    """Test all critical imports"""
    print("Testing imports after restructure...")
    print("=" * 60)

    try:
        # Test core config
        print("✓ Testing core.config...")
        from core.config import settings

        print(f"  - Settings loaded: API prefix = {settings.api_v1_prefix}")

        # Test core models
        print("✓ Testing core.models...")
        from core.models import (
            Base,
            DatabaseHelper,
            db_helper,
            InstagramComment,
            CommentClassification,
            QuestionAnswer,
            Media,
        )

        print(f"  - All models imported successfully")
        print(
            f"  - Database URL: {settings.db.url[:30]}..."
            if settings.db.url
            else "  - No DB URL set"
        )

        # Test core services
        print("✓ Testing core.services...")
        from core.services.answer_service import QuestionAnswerService
        from core.services.classification_service import CommentClassificationService
        from core.services.instagram_service import InstagramGraphAPIService
        from core.services.media_service import MediaService

        print(f"  - All services imported successfully")

        # Test API routes
        print("✓ Testing api_v1...")
        from api_v1 import router as api_router
        from api_v1.docs.views import create_docs_router

        print(f"  - API routers imported successfully")

        # Test celery
        print("✓ Testing celery_worker...")
        from core.celery_app import celery_app

        print(f"  - Celery app imported successfully")

        # Test tasks
        print("✓ Testing tasks...")
        from core.tasks.classification_tasks import classify_comment_task
        from core.tasks.answer_tasks import generate_answer_task
        from core.tasks.instagram_reply_tasks import send_instagram_reply_task

        print(f"  - All tasks imported successfully")

        # Test conversation database path
        print("✓ Testing conversation database setup...")
        qa_service = QuestionAnswerService()
        print(f"  - Conversation DB path: {qa_service.db_path}")
        print(
            f"  - Conversation DB directory exists: {Path(qa_service.db_path).parent.exists()}"
        )

        print("=" * 60)
        print("✅ ALL IMPORTS SUCCESSFUL!")
        print("=" * 60)

        return True

    except Exception as e:
        print(f"\n❌ IMPORT ERROR: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_imports()
    sys.exit(0 if success else 1)
