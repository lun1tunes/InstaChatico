import os

from pydantic import BaseModel
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class DbSettings(BaseModel):
    url: str = f"postgresql+asyncpg://instagram_user:instagram_password@localhost:5432/instagram_db"
    # echo: bool = False
    echo: bool = True


class Settings(BaseSettings):
    api_v1_prefix: str = "/api/v1"
    app_secret = os.getenv("APP_SECRET", "")
    app_webhook_verify_token = os.getenv("TOKEN", "token")
    db: DbSettings = DbSettings()


settings = Settings()
