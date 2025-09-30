from fastapi import APIRouter

from .comment_webhooks.views import router as webhooks_router
from .telegram.views import router as telegram_router


router = APIRouter()
router.include_router(router=webhooks_router, prefix="/webhook")
router.include_router(router=telegram_router, prefix="/telegram")
