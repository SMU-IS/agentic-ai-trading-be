import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    mongodb_url: str = os.getenv("MONGODB_URL", "MONGODB_URL_STRING")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
