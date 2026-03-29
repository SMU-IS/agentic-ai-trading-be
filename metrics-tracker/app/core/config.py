import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENV_PATH = os.path.join(BASE_DIR, ".env")


class EnvConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_PATH, env_file_encoding="utf-8", extra="ignore"
    )

    redis_host: str = Field(..., validation_alias="REDIS_HOST")
    redis_port: int = Field(..., validation_alias="REDIS_PORT")
    redis_password: str = Field(..., validation_alias="REDIS_PASSWORD")

    aws_access_key_id: str = Field(..., validation_alias="AWS_BUCKET_ACCESS_KEY")
    aws_secret_access_key: str = Field(..., validation_alias="AWS_BUCKET_SECRET")
    aws_region: str = Field(..., validation_alias="AWS_REGION")
    aws_bucket_name: str = Field(..., validation_alias="AWS_BUCKET_NAME")


env_config = EnvConfig()  # type: ignore
