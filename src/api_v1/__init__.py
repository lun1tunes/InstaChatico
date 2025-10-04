from fastapi import APIRouter
import logging

from .comment_webhooks.views import router as webhooks_router
from .telegram.views import router as telegram_router

logger = logging.getLogger(__name__)

router = APIRouter()
router.include_router(router=webhooks_router, prefix="/webhook")
router.include_router(router=telegram_router, prefix="/telegram")

# Try to load documents router (requires boto3, docling)
try:
    from .documents.views import router as documents_router
    router.include_router(router=documents_router)
    logger.info("Document management endpoints loaded")
except ImportError as e:
    logger.warning(f"Document management endpoints not available: {e}")
