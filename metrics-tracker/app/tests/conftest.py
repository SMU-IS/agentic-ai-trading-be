import sys
import os
from unittest.mock import MagicMock

# Mock boto3 before any app module imports it
sys.modules.setdefault("boto3", MagicMock())

os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")
os.environ.setdefault("REDIS_PASSWORD", "")
os.environ.setdefault("AWS_BUCKET_ACCESS_KEY", "test-key")
os.environ.setdefault("AWS_BUCKET_SECRET", "test-secret")
os.environ.setdefault("AWS_REGION", "ap-southeast-1")
os.environ.setdefault("AWS_BUCKET_NAME", "test-bucket")
