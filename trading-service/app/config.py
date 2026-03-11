from pydantic_settings import BaseSettings
from functools import lru_cache
import os

class Settings(BaseSettings):
    alpaca_api_key: str = os.getenv("ALPACA_API_KEY", "YOUR ALPACA KEY")
    alpaca_api_secret: str = os.getenv("ALPACA_API_SECRET", "YOUR ALPACA SECRETS")
    alpaca_paper: bool = os.getenv("ALPACA_PAPER", True)

    mongodb_url: str = os.getenv("MONGODB_URL", "MONGODB_URL_STRING")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()