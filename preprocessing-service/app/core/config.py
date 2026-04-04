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

    # Redis
    redis_host: str = Field(..., validation_alias="REDIS_HOST")
    redis_port: int = Field(..., validation_alias="REDIS_PORT")
    redis_password: str = Field(..., validation_alias="REDIS_PASSWORD")
    redis_news_stream: str = Field(..., validation_alias="NEWS_STREAM")
    redis_preproc_stream: str = Field(..., validation_alias="PREPROC_STREAM")
    post_timestamp_key: str = Field(default="post_timestamps", validation_alias="POST_TIMESTAMP_KEY")

env_config = EnvConfig()  # type: ignore
config = env_config  # Alias for backward compatibility
