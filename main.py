import os
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import HTMLResponse, PlainTextResponse
import hmac
import hashlib
from typing import List, Dict, Any
from dotenv import load_dotenv

app = FastAPI()

# Конфигурация из переменных окружения
load_dotenv()
APP_SECRET = os.getenv("APP_SECRET", "")
TOKEN = os.getenv("TOKEN", "token")
received_updates: List[Dict[Any, Any]] = []


# Middleware для проверки X-Hub подписи
@app.middleware("http")
async def verify_x_hub_signature(request: Request, call_next):
    if request.method == "POST" and any(
        request.url.path.endswith(path)
        for path in ["/facebook", "/instagram", "/threads"]
    ):
        signature = request.headers.get("X-Hub-Signature")
        if not signature:
            raise HTTPException(status_code=401, detail="Missing X-Hub-Signature")

        # Генерируем ожидаемую подпись
        body = await request.body()
        expected_signature = (
            "sha1=" + hmac.new(APP_SECRET.encode(), body, hashlib.sha1).hexdigest()
        )

        # Сравниваем подписи
        if not hmac.compare_digest(signature, expected_signature):
            raise HTTPException(status_code=401, detail="Invalid signature")

        # Возвращаем тело запроса для дальнейшей обработки
        request.state.body = body
    return await call_next(request)


# @app.get("/", response_class=HTMLResponse)
# async def root():
#     return f"<pre>{received_updates}</pre>"


@app.get("/")
@app.get("/facebook")
@app.get("/instagram")
@app.get("/threads")
async def verify_webhook(request: Request):
    if (
        request.query_params.get("hub.mode") == "subscribe"
        and request.query_params.get("hub.verify_token") == TOKEN
    ):
        return PlainTextResponse(request.query_params["hub.challenge"])
    raise HTTPException(status_code=400)


@app.post("/")
async def handle_facebook_update(request: Request):
    body = await request.json()
    print("Facebook request body:", body)
    received_updates.insert(0, body)
    return status.HTTP_200_OK


@app.post("/facebook")
async def handle_facebook_update(request: Request):
    body = await request.json()
    print("Facebook request body:", body)
    received_updates.insert(0, body)
    return status.HTTP_200_OK


@app.post("/instagram")
async def handle_instagram_update(request: Request):
    body = await request.json()
    print("Instagram request body:", body)
    received_updates.insert(0, body)
    return status.HTTP_200_OK


@app.post("/threads")
async def handle_threads_update(request: Request):
    body = await request.json()
    print("Threads request body:", body)
    received_updates.insert(0, body)
    return status.HTTP_200_OK


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "4291"))
    host = os.getenv("HOST", "0.0.0.0")  # Allow external connections
    uvicorn.run("main:app", host=host, port=port, reload=os.getenv("ENV") == "development")
