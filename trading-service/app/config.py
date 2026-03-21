import os
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    alpaca_api_key: str = os.getenv("ALPACA_API_KEY", "")
    alpaca_api_secret: str = os.getenv("ALPACA_API_SECRET", "")
    alpaca_paper: bool = os.getenv("ALPACA_PAPER", "true").lower() == "true"

    mongodb_uri: str = os.getenv("MONGODB_URI") or "mongodb://mongo:27017"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
