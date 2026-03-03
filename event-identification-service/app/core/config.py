import os
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.constant import StorageProviders

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENV_PATH = os.path.join(BASE_DIR, ".env")


class EnvConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_PATH, env_file_encoding="utf-8", extra="ignore"
    )
    
    # S3
    aws_bucket_access_key: str = Field(..., validation_alias="AWS_BUCKET_ACCESS_KEY")
    aws_bucket_secret: str = Field(..., validation_alias="AWS_BUCKET_SECRET")
    aws_region: str = Field(..., validation_alias="AWS_REGION")
    aws_bucket_name: str = Field(..., validation_alias="AWS_BUCKET_NAME")
    aws_bucket_events_key: str = Field(..., validation_alias="EVENTS_KEY")

    # Redis
    redis_host: str = Field(..., validation_alias="REDIS_HOST")
    redis_port: int = Field(..., validation_alias="REDIS_PORT")
    redis_password: str = Field(..., validation_alias="REDIS_PASSWORD")
    redis_ticker_stream: str = Field(..., validation_alias="TICKER_STREAM")
    redis_event_stream: str = Field(..., validation_alias="EVENT_STREAM")

    # Groq
    groq_api_key: Optional[str] = Field(default=None, validation_alias="GROQ_API_KEY")
    groq_model_name: str = Field(default="llama-3.3-70b-versatile", validation_alias="LARGE_LANGUAGE_MODEL_GROQ")

env_config = EnvConfig()  # type: ignore
config = env_config  # Alias for backward compatibility
