import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    redis_url: str = "redis://localhost:6379"
    sentiment_threshold: float = 0.85
    volume_threshold: int = 5
    hours_window: int = 1
    pplx_api_key: str = os.getenv("PPLX_API_KEY", "your-default-api-key")
    qdrant_url: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    qdrant_api_key: str = os.getenv("QDRANT_API_KEY", "your-default-qdrant-api-key")
    qdrant_news_collection: str = os.getenv("QDRANT_NEWS_COLLECTION", "news_analysis_compiled")
    news_stream: str = os.getenv("NEWS_STREAM", "news:sentiment")
    signal_queue: str = os.getenv("SIGNAL_QUEUE", "trading:signals")

    aggregator_base_url: str = os.getenv("AGGREGATOR_BASE_URL", "http://localhost:8000/api/v1/trading")
    class Config:
        env_file = ".env"

settings = Settings()
