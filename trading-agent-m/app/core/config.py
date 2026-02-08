import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENV_PATH = os.path.join(BASE_DIR, ".env")


class EnvConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_PATH, env_file_encoding="utf-8", extra="ignore"
    )

    # LLM
    ollama_base_url: str = Field(..., validation_alias="OLLAMA_BASE_URL")
    ollama_temperature: float = Field(..., validation_alias="TEMPERATURE")
    large_language_model: str = Field(..., validation_alias="LARGE_LANGUAGE_MODEL")

    # Redis Stream
    # redis_url: str = Field(..., validation_alias="REDIS_URL")
    # redis_worker_name: str = Field(..., validation_alias="REDIS_WORKER_NAME")
    # redis_stream_key: str = Field(..., validation_alias="REDIS_STREAM_KEY")
    # redis_group_name: str = Field(..., validation_alias="REDIS_GROUP_NAME")

    qdrant_url: str = Field(..., validation_alias="QDRANT_URL")


env_config = EnvConfig()  # type: ignore
