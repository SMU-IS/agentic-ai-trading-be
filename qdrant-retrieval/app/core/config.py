import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENV_PATH = os.path.join(BASE_DIR, ".env")


class EnvConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_PATH, env_file_encoding="utf-8", extra="ignore"
    )

    # LLM (for embeddings)
    llm_provider: str = Field(..., validation_alias="LLM_PROVIDER")
    gemini_api_key: str = Field(..., validation_alias="GEMINI_API_KEY")
    text_embedding_model: str = Field(
        default="nomic-embed-text-v1.5", validation_alias="TEXT_EMBEDDING_MODEL"
    )
    nomic_api_key: str = Field(..., validation_alias="NOMIC_API_KEY")

    # Local LLM (Ollama)
    ollama_base_url: str = Field(..., validation_alias="OLLAMA_BASE_URL")

    # Vector Store
    storage_provider: str = Field(..., validation_alias="STORAGE_PROVIDER")
    qdrant_api_key: str = Field(..., validation_alias="QDRANT_API_KEY")
    qdrant_url: str = Field(..., validation_alias="QDRANT_URL")

    # Redis
    redis_host: str = Field(..., validation_alias="REDIS_HOST")
    redis_port: int = Field(..., validation_alias="REDIS_PORT")
    redis_password: str = Field(..., validation_alias="REDIS_PASSWORD")
    redis_sentiment_stream: str = Field(..., validation_alias="SENTIMENT_STREAM")
    redis_aggregator_stream: str = Field(..., validation_alias="AGGREGATOR_STREAM")

    # Postgres
    postgres_host: str = Field(..., validation_alias="POSTGRES_HOST")
    postgres_user: str = Field(..., validation_alias="POSTGRES_USER")
    postgres_port: str = Field(..., validation_alias="POSTGRES_PORT")
    postgres_db: str = Field(..., validation_alias="POSTGRES_DB")




env_config = EnvConfig()  # type: ignore
