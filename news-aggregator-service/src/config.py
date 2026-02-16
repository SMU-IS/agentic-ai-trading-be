import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    redis_host: str = os.getenv("REDIS_HOST", "localhost:6379")
    redis_port: str = os.getenv("REDIS_PORT", "17989")
    redis_password: str =os.getenv("REDIS_PASSWORD", "password")

    redis_news_stream: str = os.getenv("REDIS_NEWS_STREAM", "news_notification_stream")
    redis_signal_stream: str = os.getenv("REDIS_SIGNAL_STREAM", "trading_signal_stream")
    redis_sentiment_stream: str = os.getenv("REDIS_SENTIMENT_STREAM", "sentiment_stream")
    redis_aggregator_stream: str = os.getenv("REDIS_AGGREGATOR_STREAM", "news_aggregator_stream")

    sentiment_threshold: float = 0.85
    volume_threshold: int = 5
    hours_window: int = 1
    pplx_api_key: str = os.getenv("PPLX_API_KEY", "your-default-api-key")
    qdrant_url: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    qdrant_api_key: str = os.getenv("QDRANT_API_KEY", "your-default-qdrant-api-key")
    qdrant_news_collection: str = os.getenv("QDRANT_NEWS_COLLECTION", "news_analysis_compiled")

    aggregator_base_url: str = os.getenv("AGGREGATOR_BASE_URL", "http://localhost:8000/api/v1/trading")
    class Config:
        env_file = ".env"

settings = Settings()
