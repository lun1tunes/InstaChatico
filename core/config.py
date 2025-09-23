import os
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class DbSettings(BaseModel):
    url: str = os.getenv("DATABASE_URL")
    echo: bool = True

class CelerySettings(BaseModel):
    broker_url: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    result_backend: str = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

class OpenAISettings(BaseModel):
    api_key: str = os.getenv("OPENAI_API_KEY", "")
    model: str = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
    rpm_limit: int = int(os.getenv("OPENAI_RPM_LIMIT", "50"))
    tpm_limit: int = int(os.getenv("OPENAI_TPM_LIMIT", "100000"))

class InstagramSettings(BaseModel):
    access_token: str = os.getenv("INSTA_TOKEN", "")
    api_version: str = os.getenv("INSTAGRAM_API_VERSION", "v18.0")
    base_url: str = f"https://graph.facebook.com/{os.getenv('INSTAGRAM_API_VERSION', 'v18.0')}"

class Settings(BaseSettings):
    api_v1_prefix: str = "/api/v1"
    app_secret: str = os.getenv("APP_SECRET", "app_secret").strip()
    app_webhook_verify_token: str = os.getenv("TOKEN", "token").strip()
    db: DbSettings = DbSettings()
    celery: CelerySettings = CelerySettings()
    openai: OpenAISettings = OpenAISettings()
    instagram: InstagramSettings = InstagramSettings()

settings = Settings()
