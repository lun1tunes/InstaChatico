from fastapi import APIRouter

from .comment_webhooks.views import router as webhooks_router
from .question_answers.views import router as answers_router

router = APIRouter()
router.include_router(router=webhooks_router, prefix="/webhook")
router.include_router(router=answers_router, prefix="/question-answers")