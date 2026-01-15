from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    alpaca_api_key: str
    alpaca_api_secret: str
    alpaca_paper: bool = True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()