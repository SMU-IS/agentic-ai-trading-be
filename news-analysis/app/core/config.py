import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.constant import StorageProviders

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENV_PATH = os.path.join(BASE_DIR, ".env")


class EnvConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_PATH, env_file_encoding="utf-8", extra="ignore"
    )

    # S3
    aws_bucket_access_key: str = Field(..., validation_alias="AWS_BUCKET_ACCESS_KEY")
    aws_bucket_secret: str = Field(..., validation_alias="AWS_BUCKET_SECRET")
    aws_region: str = Field(..., validation_alias="AWS_REGION")
    aws_bucket_name: str = Field(..., validation_alias="AWS_BUCKET_NAME")
    aws_bucket_cleaned_key: str = Field(..., validation_alias="CLEANED_KEY")
    aws_bucket_alias_key: str = Field(..., validation_alias="ALIAS_KEY")
    aws_bucket_events_key: str = Field(..., validation_alias="EVENTS_KEY")
    aws_bucket_removed_key: str = Field(..., validation_alias="REMOVED_KEY")


    # Redis
    redis_url: str = Field(..., validation_alias="REDIS_URL")
    redis_news_queue: str = Field(..., validation_alias="REDIS_QUEUE_NAME")
    redis_host: str = Field(..., validation_alias="REDIS_HOST")
    redis_port: str = Field(..., validation_alias="REDIS_PORT")
    redis_password: str = Field(..., validation_alias="REDIS_PASSWORD")
    redis_reddit_stream: str =  Field(..., validation_alias="REDDIT_STREAM")
    redis_preproc_stream: str =  Field(..., validation_alias="PREPROC_STREAM")
    redis_ticker_stream: str =  Field(..., validation_alias="TICKER_STREAM")
    redis_event_stream: str =  Field(..., validation_alias="EVENT_STREAM")
    redis_credibility_stream: str =  Field(..., validation_alias="CREDIBILITY_STREAM")
    redis_sentiment_stream: str =  Field(..., validation_alias="SENTIMENT_STREAM")


    # LLM
    llm_provider: str = Field(..., validation_alias="LLM_PROVIDER")
    ollama_base_url: str = Field(..., validation_alias="OLLAMA_BASE_URL")
    open_ai_api_key: str = Field(..., validation_alias="OPEN_AI_API_KEY")
    text_embedding_model: str = Field(..., validation_alias="TEXT_EMBEDDING_MODEL")
    large_language_model: str = Field(..., validation_alias="LARGE_LANGUAGE_MODEL")
    max_completion_tokens: int = Field(..., validation_alias="MAX_COMPLETION_TOKEN")

    # Vector Store
    storage_provider: StorageProviders = Field(..., validation_alias="STORAGE_PROVIDER")
    qdrant_url: str = Field(..., validation_alias="QDRANT_URL")


env_config = EnvConfig()  # type: ignore
config = env_config  # Alias for backward compatibility
