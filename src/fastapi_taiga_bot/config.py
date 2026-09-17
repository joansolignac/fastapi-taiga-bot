from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    telegram_token: str = Field(alias="TELEGRAM_BOT_TOKEN")
    telegram_webhook_secret: str = Field(alias="TELEGRAM_WEBHOOK_SECRET")
    
    taiga_base_url: str =  Field(alias="TAIGA_BASE_URL")
    taiga_web_base_url: str = Field(alias="TAIGA_WEB_BASE_URL")
    
    database_url: str = Field(alias="DATABASE_URL")

    taiga_token_encryption_key: str = Field(alias="TAIGA_TOKEN_ENCRYPTION_KEY")

    taiga_webhook_secret: str = Field(alias="TAIGA_WEBHOOK_SECRET")

    taiga_admin_username: str = Field(alias="TAIGA_ADMIN_USERNAME")
    taiga_admin_password: str = Field(alias="TAIGA_ADMIN_PASSWORD")

    model_config  = SettingsConfigDict(
        env_file=".env",
        populate_by_name=True
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()