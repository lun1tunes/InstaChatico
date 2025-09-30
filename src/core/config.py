import os
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class DbSettings(BaseModel):
    url: str = os.getenv("DATABASE_URL")
    echo: bool = False
    # echo: bool = True


class CelerySettings(BaseModel):
    broker_url: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    result_backend: str = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")


class OpenAISettings(BaseModel):
    api_key: str = os.getenv("OPENAI_API_KEY", "")
    model_comment_classification: str = os.getenv("OPENAI_MODEL_CLASSIFICATION", "gpt-5-nano")
    model_comment_response: str = os.getenv("OPENAI_MODEL_RESPONSE", "gpt-5-mini")
    rpm_limit: int = int(os.getenv("OPENAI_RPM_LIMIT", "50"))
    tpm_limit: int = int(os.getenv("OPENAI_TPM_LIMIT", "100000"))


class InstagramSettings(BaseModel):
    access_token: str = os.getenv("INSTA_TOKEN", "")
    api_version: str = os.getenv("INSTAGRAM_API_VERSION", "v23.0")
    base_url: str = f"https://graph.instagram.com/{os.getenv('INSTAGRAM_API_VERSION', 'v23.0')}"
    bot_username: str = os.getenv("INSTAGRAM_BOT_USERNAME", "")


class TelegramSettings(BaseModel):
    bot_token: str = os.getenv("TG_TOKEN", "")
    chat_id: str = os.getenv("TG_CHAT_ID", "")
    tg_chat_alerts_thread_id: str = os.getenv("TG_CHAT_ALERTS_THREAD_ID", "")
    tg_chat_logs_thread_id: str = os.getenv("TG_CHAT_LOGS_THREAD_ID", "")


class HealthSettings(BaseModel):
    cpu_warn_pct: int = int(os.getenv("HEALTH_CPU_WARN_PCT", "85"))
    mem_warn_pct: int = int(os.getenv("HEALTH_MEM_WARN_PCT", "85"))
    disk_warn_pct: int = int(os.getenv("HEALTH_DISK_WARN_PCT", "90"))
    check_interval_seconds: int = int(os.getenv("HEALTH_CHECK_INTERVAL_SECONDS", "600"))


class DocsSettings(BaseModel):
    username: str = os.getenv("DOCS_USERNAME", "")
    password: str = os.getenv("DOCS_PASSWORD", "")


class Settings(BaseSettings):
    api_v1_prefix: str = "/api/v1"
    app_secret: str = os.getenv("APP_SECRET", "app_secret").strip()
    app_webhook_verify_token: str = os.getenv("TOKEN", "token").strip()
    db: DbSettings = DbSettings()
    celery: CelerySettings = CelerySettings()
    openai: OpenAISettings = OpenAISettings()
    instagram: InstagramSettings = InstagramSettings()
    telegram: TelegramSettings = TelegramSettings()
    health: HealthSettings = HealthSettings()
    docs: DocsSettings = DocsSettings()


settings = Settings()
