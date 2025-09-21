import os
import logging 
import hashlib
import hmac

import uvicorn

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException

from core.config import settings
from api_v1 import router as router_v1


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    

app = FastAPI(lifespan=lifespan)
app.include_router(router=router_v1, prefix=settings.api_v1_prefix)


# Middleware для проверки X-Hub подписи
@app.middleware("http")
async def verify_webhook_signature(request: Request, call_next):
    if request.method == "POST" and request.url.path == "/webhook/instagram":
        signature = request.headers.get("X-Hub-Signature")
        if not signature:
            raise HTTPException(status_code=401, detail="Missing signature")
        
        body = await request.body()
        expected_signature = "sha1=" + hmac.new(
            APP_SECRET.encode(),
            body,
            hashlib.sha1
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_signature):
            raise HTTPException(status_code=401, detail="Invalid signature")
        
        # Сохраняем тело запроса для дальнейшей обработки
        request.state.body = body
        return await call_next(request)
    
    return await call_next(request)

if __name__ == "__main__":

    port = int(os.getenv("PORT"))
    host = os.getenv("HOST", "0.0.0.0")  # Allow external connections
    uvicorn.run("main:app", host=host, port=port, reload=True)
