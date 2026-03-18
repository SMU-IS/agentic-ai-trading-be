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

    # Redis
    redis_host: str = Field(..., validation_alias="REDIS_HOST")
    redis_port: int = Field(..., validation_alias="REDIS_PORT")
    redis_password: str = Field(..., validation_alias="REDIS_PASSWORD")
    redis_news_stream: str = Field(..., validation_alias="NEWS_STREAM")
    redis_preproc_stream: str = Field(..., validation_alias="PREPROC_STREAM")

env_config = EnvConfig()  # type: ignore
config = env_config  # Alias for backward compatibility
