import os

# from app.core.constant import LLMProviders, StorageProviders
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENV_PATH = os.path.join(BASE_DIR, ".env")


class EnvConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_PATH, env_file_encoding="utf-8", extra="ignore"
    )

    # LLM
    # llm_provider: LLMProviders = Field(..., validation_alias="LLM_PROVIDER")
    ollama_base_url: str = Field(..., validation_alias="OLLAMA_BASE_URL")
    open_ai_api_key: str = Field(..., validation_alias="OPEN_AI_API_KEY")
    text_embedding_model: str = Field(..., validation_alias="TEXT_EMBEDDING_MODEL")
    large_language_model: str = Field(..., validation_alias="LARGE_LANGUAGE_MODEL")
    max_completion_tokens: int = Field(..., validation_alias="MAX_COMPLETION_TOKEN")

    # Vector Store
    # storage_provider: StorageProviders = Field(..., validation_alias="STORAGE_PROVIDER")
    qdrant_url: str = Field(..., validation_alias="QDRANT_URL")


env_config = EnvConfig()  # type: ignore
