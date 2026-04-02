import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    mongodb_url: str = os.getenv("MONGODB_URL", "MONGODB_URL_STRING")
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
