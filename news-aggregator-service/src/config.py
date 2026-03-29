import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_host: str = os.getenv("REDIS_HOST", "localhost:6379")
    redis_port: str = os.getenv("REDIS_PORT", "17989")
    redis_password: str = os.getenv("REDIS_PASSWORD", "password")

    redis_news_stream: str = os.getenv("REDIS_NEWS_STREAM", "news_notification_stream")
    redis_signal_stream: str = os.getenv("REDIS_SIGNAL_STREAM", "trading_signal_stream")
    redis_sentiment_stream: str = os.getenv(
        "REDIS_SENTIMENT_STREAM", "sentiment_stream"
    )
    redis_aggregator_stream: str = os.getenv(
        "REDIS_AGGREGATOR_STREAM", "news_aggregator_stream"
    )
    sentiment_min_threshold: float = 0.2
    sentiment_threshold: float = 0.75
    volume_threshold: int = 8
    hours_window: int = 1
    ## LLM
    model: str = os.getenv("MODEL", "sonar")
    pplx_api_key: str = os.getenv("PPLX_API_KEY", "your-default-api-key")
    groq_api_key: str = os.getenv("GROQ_API_KEY", "your-default-api-key")
    llm_provider: str = os.getenv("LLM_PROVIDER", "groq")
    
    news_analysis_qdrant_url: str = os.getenv(
        "NEWS_ANALYSIS_QDRANT_URL",
        "http://qdrant-retrieval-infra:5009/qdrant/ticker-events",
    )
    aggregator_base_url: str = os.getenv(
        "AGGREGATOR_BASE_URL", "http://localhost:8000/api/v1/trading"
    )
    redis_service_control_key: str = os.getenv(
        "REDIS_SERVICE_CONTROL_KEY", "services:news-aggregator-service"
    )

    class Config:
        env_file = ".env"


settings = Settings()
