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
    redis_sentiment_stream: str = Field(..., validation_alias="SENTIMENT_STREAM")
    redis_event_stream: str = Field(..., validation_alias="EVENT_STREAM")

    # Ollama (local)
    ollama_modelname: str = Field(default="llama3:8b", validation_alias="LARGE_LANGUAGE_MODEL_LLAMA_LOCAL")
    ollama_baseurl: str = Field(default="http://localhost:11434", validation_alias="OLLAMA_BASE_URL")

    # Groq
    groq_api_key: Optional[str] = Field(default=None, validation_alias="GROQ_API_KEY")
    groq_model_name: str = Field(default="llama-3.3-70b-versatile", validation_alias="LARGE_LANGUAGE_MODEL_LLAMA")

env_config = EnvConfig()  # type: ignore
config = env_config  # Alias for backward compatibility
