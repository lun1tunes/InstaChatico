from fastapi import APIRouter

from .comment_webhooks.views import router as webhooks_router

router = APIRouter()
router.include_router(router=webhooks_router, prefix="/webhook")