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
    redis_host: str = Field(..., validation_alias="REDIS_HOST")
    redis_port: int = Field(..., validation_alias="REDIS_PORT")
    redis_stream_name: str = Field("tradingview_stream", validation_alias="REDIS_STREAM")
    redis_password: str = Field("", validation_alias="REDIS_PASSWORD")

    # Scraper control
    auto_scrape: bool = Field(True, validation_alias="AUTO_SCRAPE")


env_config = EnvConfig()
config = env_config
