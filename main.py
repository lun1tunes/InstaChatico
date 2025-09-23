import os
import logging 
import hashlib
import hmac

import uvicorn

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

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
    # Check if this is a POST request to the webhook endpoint (with or without trailing slash)
    webhook_path = "/api/v1/webhook"
    if request.method == "POST" and request.url.path.rstrip("/") == webhook_path:
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
                logging.error("Signature verification failed!")
                logging.error(f"Body length: {len(body)}")
                logging.error(f"Signature header used: {'X-Hub-Signature-256' if signature_256 else 'X-Hub-Signature'}")
                logging.error(f"Signature prefix: {signature[:10]}..." if len(signature) > 10 else "Signature: [REDACTED]")
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid signature"}
                )
            else:
                logging.info("Signature verification successful")
        else:
            # Check if we're in development mode (allow requests without signature for testing)
            development_mode = os.getenv("DEVELOPMENT_MODE", "false").lower() == "true"
            
            if development_mode:
                logging.warning("DEVELOPMENT MODE: Allowing webhook request without signature header")
            else:
                # Block requests without signature headers in production
                logging.error("Webhook request received without X-Hub-Signature or X-Hub-Signature-256 header - blocking request")
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Missing signature header"}
                )
        
        # Сохраняем тело запроса для дальнейшей обработки
        request.state.body = body
        return await call_next(request)
    
    return await call_next(request)

if __name__ == "__main__":

    port = int(os.getenv("PORT"))
    host = os.getenv("HOST", "0.0.0.0")  # Allow external connections
    uvicorn.run("main:app", host=host, port=port, reload=True)
