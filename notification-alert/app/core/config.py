import os
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENV_PATH = os.path.join(BASE_DIR, ".env")

class EnvConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_PATH,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    redis_host: str = Field(..., validation_alias="REDIS_HOST")
    redis_port: int = Field(..., validation_alias="REDIS_PORT")
    redis_notification_stream: str = Field(..., validation_alias="REDIS_NOTIFICATION_STREAM")
    redis_sentiment_stream: str = Field(..., validation_alias="REDIS_SENTIMENT_STREAM")
    redis_analysis_stream: str = Field(..., validation_alias="REDIS_ANALYSIS_STREAM")
    redis_password: str = Field(..., validation_alias="REDIS_PASSWORD")

env_config = EnvConfig()
config = env_config 
