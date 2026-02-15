import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import final

from app.core.constant import LLMProviders

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENV_PATH = os.path.join(BASE_DIR, ".env")


@final
class EnvConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_PATH, env_file_encoding="utf-8", extra="ignore"
    )

    llm_provider: LLMProviders = Field(..., validation_alias="LLM_PROVIDER")
    large_language_model: str = Field(..., validation_alias="LARGE_LANGUAGE_MODEL")
    max_completion_tokens: int = Field(..., validation_alias="MAX_COMPLETION_TOKEN")
    temperature: float = Field(..., validation_alias="TEMPERATURE")

    # Gemini
    gemini_api_key: str | None = Field(None, validation_alias="GEMINI_API_KEY")

    # Ollama
    ollama_base_url: str | None = Field(None, validation_alias="OLLAMA_BASE_URL")
    open_ai_api_key: str | None = Field(None, validation_alias="OPEN_AI_API_KEY")

    # Groq
    groq_api_key: str = Field(..., validation_alias="GROQ_API_KEY")

    # Qdrant News Analysis
    news_analysis_query_url: str = Field(
        ..., validation_alias="NEWS_ANALYSIS_QUERY_URL"
    )

    # AWS
    aws_access_key_id: str = Field(..., validation_alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str = Field(..., validation_alias="AWS_SECRET_ACCESS_KEY")
    aws_bucket_name: str = Field(..., validation_alias="AWS_S3_BUCKET_NAME")
    aws_file_name: str = Field(..., validation_alias="AWS_S3_FILE_NAME")


env_config = EnvConfig()  # type: ignore
