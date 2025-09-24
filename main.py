import os
import hashlib
import hmac

import uvicorn

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

from core.config import settings
from core.logging_config import setup_logging, get_logger
from api_v1 import router as router_v1

# Initialize logging
setup_logging(
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    log_format=os.getenv("LOG_FORMAT", "structured"),
    log_file=os.getenv("LOG_FILE")
)

# Get logger for main application
logger = get_logger(__name__, "main_app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("Starting InstaChatico application")
    yield
    logger.info("Shutting down InstaChatico application")
    

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
                logger.error(
                    "Webhook signature verification failed",
                    extra_fields={
                        "body_length": len(body),
                        "signature_header": "X-Hub-Signature-256" if signature_256 else "X-Hub-Signature",
                        "signature_prefix": signature[:10] + "..." if len(signature) > 10 else "[REDACTED]"
                    },
                    operation="signature_verification"
                )
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid signature"}
                )
            else:
                logger.info(
                    "Webhook signature verification successful",
                    extra_fields={
                        "body_length": len(body),
                        "signature_type": "SHA256" if signature_256 else "SHA1"
                    },
                    operation="signature_verification"
                )
        else:
            # Check if we're in development mode (allow requests without signature for testing)
            development_mode = os.getenv("DEVELOPMENT_MODE", "false").lower() == "true"
            
            if development_mode:
                logger.warning(
                    "DEVELOPMENT MODE: Allowing webhook request without signature header",
                    operation="signature_verification"
                )
            else:
                # Block requests without signature headers in production
                logger.error(
                    "Webhook request received without signature header - blocking request",
                    operation="signature_verification"
                )
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Missing signature header"}
                )
        
        # Сохраняем тело запроса для дальнейшей обработки
        request.state.body = body
        return await call_next(request)
    
    return await call_next(request)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "4291"))
    host = os.getenv("HOST", "0.0.0.0")  # Allow external connections
    
    logger.info(
        "Starting InstaChatico server",
        extra_fields={
            "host": host,
            "port": port,
            "environment": os.getenv("ENVIRONMENT", "development")
        }
    )
    
    uvicorn.run("main:app", host=host, port=port, reload=True)
