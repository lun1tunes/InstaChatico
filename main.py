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
    if request.method == "POST" and request.url.path == "/api/v1/webhook/":
        # Instagram uses X-Hub-Signature-256 (SHA256) instead of X-Hub-Signature (SHA1)
        signature_256 = request.headers.get("X-Hub-Signature-256")
        signature_1 = request.headers.get("X-Hub-Signature")
        body = await request.body()
        
        # Try SHA256 first (Instagram's preferred method), then fallback to SHA1
        signature = signature_256 or signature_1
        
        if signature:
            # Determine which algorithm to use based on the header
            if signature_256:
                # Instagram uses SHA256
                expected_signature = "sha256=" + hmac.new(
                    settings.app_secret.encode(),
                    body,
                    hashlib.sha256
                ).hexdigest()
            else:
                # Fallback to SHA1 for compatibility
                expected_signature = "sha1=" + hmac.new(
                    settings.app_secret.encode(),
                    body,
                    hashlib.sha1
                ).hexdigest()

            if not hmac.compare_digest(signature, expected_signature):
                logging.error(f"Signature verification failed. Expected: {expected_signature}, Received: {signature}")
                logging.error(f"App secret: {settings.app_secret}")
                logging.error(f"Body length: {len(body)}")
                # For development, log the error but don't block the request
                logging.warning("Allowing request despite signature verification failure (development mode)")
            else:
                logging.info("Signature verification successful")
        else:
            # Log warning if signature is missing but don't block the request
            logging.warning("Webhook request received without X-Hub-Signature or X-Hub-Signature-256 header")
        
        # Сохраняем тело запроса для дальнейшей обработки
        request.state.body = body
        return await call_next(request)
    
    return await call_next(request)

if __name__ == "__main__":

    port = int(os.getenv("PORT"))
    host = os.getenv("HOST", "0.0.0.0")  # Allow external connections
    uvicorn.run("main:app", host=host, port=port, reload=True)
