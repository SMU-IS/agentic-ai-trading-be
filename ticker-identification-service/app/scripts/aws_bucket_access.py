import boto3
from app.core.config import env_config
from typing import Optional


class AWSBucket:
    def __init__(
        self,
        aws_bucket_access_key: str = env_config.aws_bucket_access_key,
        aws_bucket_secret: str = env_config.aws_bucket_secret,
        aws_region: str = env_config.aws_region,
        aws_bucket_name: str = env_config.aws_bucket_name,
    ):
        self.aws_bucket_name = aws_bucket_name

        self.s3_client = boto3.client(
            service_name="s3",
            region_name=aws_region,
            aws_access_key_id=aws_bucket_access_key,
            aws_secret_access_key=aws_bucket_secret,
        )

    # ---------- WRITE ----------

    def upload_file(
        self,
        local_path: str,
        object_key: Optional[str] = None,
    ) -> None:
        """
        Upload a local file to S3
        """
        if object_key is None:
            object_key = local_path

        self.s3_client.upload_file(
            Filename=local_path,
            Bucket=self.aws_bucket_name,
            Key=object_key,
        )

    def write_bytes(
        self,
        data: bytes,
        object_key: str,
        content_type: Optional[str] = None,
    ) -> None:
        """
        Write bytes directly to S3
        """
        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type

        self.s3_client.put_object(
            Bucket=self.aws_bucket_name,
            Key=object_key,
            Body=data,
            **extra_args,
        )

    def write_text(
        self,
        text: str,
        object_key: str,
        encoding: str = "utf-8",
    ) -> None:
        """
        Write a text file to S3
        """
        self.write_bytes(
            data=text.encode(encoding),
            object_key=object_key,
            content_type="text/plain",
        )

    # ---------- READ ----------

    def download_file(
        self,
        object_key: str,
        local_path: str,
    ) -> None:
        """
        Download an S3 object to local filesystem
        """
        self.s3_client.download_file(
            Bucket=self.aws_bucket_name,
            Key=object_key,
            Filename=local_path,
        )

    def read_bytes(self, object_key: str) -> bytes:
        """
        Read an S3 object into memory as bytes
        """
        response = self.s3_client.get_object(
            Bucket=self.aws_bucket_name,
            Key=object_key,
        )
        return response["Body"].read()

    def read_text(
        self,
        object_key: str,
        encoding: str = "utf-8",
    ) -> str:
        """
        Read an S3 object into memory as text
        """
        return self.read_bytes(object_key).decode(encoding)
