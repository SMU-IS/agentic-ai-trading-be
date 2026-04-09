from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # LLM Configuration (Groq)
    llm_provider: str = "groq"
    groq_api_key: str = Field(..., validation_alias="GROQ_API_KEY")
    model_name: str = Field(
        default="llama-3.3-70b-versatile", validation_alias="LARGE_LANGUAGE_MODEL"
    )

    # Embeddings (Nomic)
    nomic_api_key: str = Field(..., validation_alias="NOMIC_API_KEY")
    embedding_model: str = Field(
        default="nomic-embed-text-v1.5", validation_alias="TEXT_EMBEDDING_MODEL"
    )

    # Qdrant Configuration
    qdrant_api_key: str = Field(..., validation_alias="QDRANT_API_KEY")
    qdrant_url: str = Field(..., validation_alias="QDRANT_URL")
    qdrant_collection_name: str = "agent_m_knowledge_base"

    # Redis Configuration
    redis_host: str = Field(default="localhost", validation_alias="REDIS_HOST")
    redis_port: int = Field(default=6379, validation_alias="REDIS_PORT")
    redis_password: Optional[str] = Field(
        default=None, validation_alias="REDIS_PASSWORD"
    )
    redis_history_ttl: int = 3600  # 1 hour

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
