import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_env_file = os.environ.get("ENV_FILE", ".env")
_base_env = os.path.join(BASE_DIR, ".env")
_override_env = os.path.join(BASE_DIR, _env_file)
_env_files = (_base_env,) if _env_file == ".env" else (_base_env, _override_env)


class EnvConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_files, env_file_encoding="utf-8", extra="ignore"
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
    post_timestamp_key: str = Field(default="post_timestamps", validation_alias="POST_TIMESTAMP_KEY")

    # Postgres
    postgres_host: str = Field(..., validation_alias="POSTGRES_HOST")
    postgres_user: str = Field(..., validation_alias="POSTGRES_USER")
    postgres_password: str = Field(..., validation_alias="POSTGRES_PASSWORD")
    postgres_port: str = Field(..., validation_alias="POSTGRES_PORT")
    postgres_db: str = Field(..., validation_alias="POSTGRES_DB")
    postgres_ssl_mode: str = Field("verify-full", validation_alias="POSTGRES_SSL_MODE")
    postgres_ca_cert: str = Field(
        "/certs/global-bundle.pem", validation_alias="POSTGRES_CA_CERT"
    )


env_config = EnvConfig()  # type: ignore
