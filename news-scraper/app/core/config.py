import os
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENV_PATH = os.path.join(BASE_DIR, ".env")


class EnvConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_PATH,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Redis
    redis_host: str = Field("redis", validation_alias="REDIS_HOST")
    redis_port: int = Field(6379, validation_alias="REDIS_PORT")
    redis_stream_name: str = Field(
        "reddit_stream", validation_alias="REDIS_STREAM"
    )
    redis_password: str = Field(..., validate_alias="REDIS_PASSWORD")

    # Reddit API
    reddit_client_id: str = Field(..., validation_alias="REDDIT_CLIENT_ID")
    reddit_client_secret: str = Field(..., validation_alias="REDDIT_CLIENT_SECRET")
    reddit_user_agent: str = Field(
        "reddit-scraper", validation_alias="REDDIT_USER_AGENT"
    )


env_config = EnvConfig()
config = env_config 
