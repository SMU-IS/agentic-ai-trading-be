import os

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENV_PATH = os.path.join(BASE_DIR, ".env")


class EnvConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_PATH, env_file_encoding="utf-8", extra="ignore"
    )

    # Redis Stream
    redis_host: str = os.getenv("REDIS_HOST", "localhost")
    redis_port: str = os.getenv("REDIS_PORT", "17989")
    redis_password: str = os.getenv("REDIS_PASSWORD", "password")
    redis_signal_stream: str = os.getenv("REDIS_SIGNAL_STREAM", "trading_signal_stream")
    redis_trading_noti_stream: str = os.getenv("REDIS_TRADING_NOTI_STREAM", "trade_notification_stream")

    # Perplexity
    perplexity_api_key: str = os.getenv("PERPLEXITY_API_KEY", "your-default-api-key")
    perplexity_model: str = os.getenv("PERPLEXITY_MODEL", "sonar")
    perplexity_temperature: float = os.getenv("PERPLEXITY_TEMPERATURE", 0.2)

    trading_service_url : str = os.getenv("TRADING_SERVICE_URL", "http://localhost:8000/api/v1/trading")
env_config = EnvConfig()  # type: ignore
