from pydantic_settings import BaseSettings
from functools import lru_cache
import os

class Settings(BaseSettings):
    mongodb_url: str = os.getenv("MONGODB_URL", "MONGODB_URL_STRING")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()