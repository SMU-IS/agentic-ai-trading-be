from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from app.core.db import DatabaseManager
from app.core.s3_config import S3ConfigService


@pytest.fixture
def mock_boto3():
    with patch("boto3.client") as mock:
        yield mock


def test_s3_config_service_init(mock_boto3):
    _ = S3ConfigService()
    mock_boto3.assert_called_once()
    args, kwargs = mock_boto3.call_args
    assert args[0] == "s3"


def test_s3_get_file_content_success(mock_boto3):
    mock_client = mock_boto3.return_value
    mock_client.get_object.return_value = {
        "Body": MagicMock(read=lambda: b"test content")
    }

    service = S3ConfigService()
    content = service.get_file_content("bucket", "key")

    assert content == "test content"
    mock_client.get_object.assert_called_with(Bucket="bucket", Key="key")


def test_s3_get_file_content_failure(mock_boto3):
    mock_client = mock_boto3.return_value
    mock_client.get_object.side_effect = ClientError(
        {"Error": {"Code": "404"}}, "GetObject"
    )

    service = S3ConfigService()
    with pytest.raises(ClientError):
        service.get_file_content("bucket", "key")


@pytest.mark.asyncio
async def test_database_manager_get_checkpointer():
    mock_pool_instance = MagicMock()
    mock_pool_instance.__aenter__ = AsyncMock(return_value=mock_pool_instance)
    mock_pool_instance.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.core.db.AsyncConnectionPool", return_value=mock_pool_instance),
        patch("app.core.db.BotMemory") as mock_bot_memory,
    ):
        mock_bot_memory_instance = mock_bot_memory.return_value
        mock_bot_memory_instance.setup = AsyncMock()

        manager = DatabaseManager()
        async for checkpointer in manager.get_checkpointer():
            assert checkpointer == mock_bot_memory_instance
            mock_bot_memory_instance.setup.assert_called_once()
            break
