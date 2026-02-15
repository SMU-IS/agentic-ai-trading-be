import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import env_config


class S3ConfigService:
    def __init__(self):
        self.s3_client = boto3.client(
            "s3",
            aws_access_key_id=env_config.aws_access_key_id,
            aws_secret_access_key=env_config.aws_secret_access_key,
        )  # type: ignore

    def get_file_content(self, bucket: str, key: str) -> str:
        try:
            response = self.s3_client.get_object(Bucket=bucket, Key=key)
            return response["Body"].read().decode("utf-8")
        except (BotoCoreError, ClientError) as e:
            print(f"S3 Retrieval Error: {e}")
            raise
