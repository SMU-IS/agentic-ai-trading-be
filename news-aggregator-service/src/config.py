import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    redis_url: str = "redis://localhost:6379"
    news_stream: str = "news:sentiment"
    signal_queue: str = "trading:signals"
    sentiment_threshold: float = 0.85
    volume_threshold: int = 5
    hours_window: int = 1
    pplx_api_key: str = os.getenv("PPLX_API_KEY", "your-default-api-key")
    qdrant_url: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    class Config:
        env_file = ".env"

settings = Settings()
