from pydantic import BaseModel
from pydantic_settings import BaseSettings


class DbSettings(BaseModel):
    url: str = f"postgresql+asyncpg://instagram_user:instagram_password@localhost:5432/instagram_db"
    # echo: bool = False
    echo: bool = True


class Settings(BaseSettings):
    api_v1_prefix: str = "/api/v1"

    db: DbSettings = DbSettings()


settings = Settings()
