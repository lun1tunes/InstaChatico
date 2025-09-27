from fastapi import APIRouter

from .comment_webhooks.views import router as webhooks_router
from .question_answers.views import router as answers_router
from .instagram_replies.views import router as replies_router
from .telegram.views import router as telegram_router

router = APIRouter()
router.include_router(router=webhooks_router, prefix="/webhook")
router.include_router(router=answers_router, prefix="/question-answers")
router.include_router(router=replies_router, prefix="/instagram-replies")
router.include_router(router=telegram_router)