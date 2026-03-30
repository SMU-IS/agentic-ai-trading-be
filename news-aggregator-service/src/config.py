from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Redis
    redis_host: str = "localhost"
    redis_port: str = "17989"
    redis_password: str = "password"

    # Streams
    redis_news_stream: str = "news_notification_stream"
    redis_signal_stream: str = "trading_signal_stream"
    redis_sentiment_stream: str = "sentiment_stream"
    redis_aggregator_stream: str = "news_aggregator_stream"

    # Thresholds
    sentiment_min_threshold: float = 0.2
    sentiment_threshold: float = 0.75
    volume_threshold: int = 8
    hours_window: int = 1

    # LLM
    model: str = "sonar"
    pplx_api_key: str = "your-default-api-key"
    groq_api_key: str = "your-default-api-key"
    llm_provider: str = "perplexity"

    # URLs
    news_analysis_qdrant_url: str = "http://qdrant-retrieval-infra:5009/ticker-events"
    aggregator_base_url: str = "http://trading-service-infra:5007/api/v1/trading"

    # Service control
    redis_service_control_key: str = "services:news-aggregator-service"


settings = Settings()
