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
        default="text-embedding-004", validation_alias="TEXT_EMBEDDING_MODEL"
    )

    # Vector Store
    storage_provider: str = Field(..., validation_alias="STORAGE_PROVIDER")
    qdrant_api_key: str = Field(..., validation_alias="QDRANT_API_KEY")
    qdrant_url: str = Field(..., validation_alias="QDRANT_URL")


env_config = EnvConfig()  # type: ignore
