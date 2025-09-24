from fastapi import APIRouter

from .webhooks import router as webhooks_router
from .health import router as health_router

router = APIRouter()
router.include_router(router=webhooks_router, prefix="/webhook")
router.include_router(router=health_router)