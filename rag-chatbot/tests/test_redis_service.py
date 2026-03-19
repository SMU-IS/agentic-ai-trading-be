from unittest.mock import patch

import pytest
import redis

from app.services.redis_service import RedisService


@pytest.fixture
def mock_redis():
    with patch("redis.Redis") as mock:
        yield mock


def test_redis_service_init(mock_redis):
    # Setup
    mock_instance = mock_redis.return_value

    # Execute
    # service = RedisService()

    # Assert
    mock_redis.assert_called_once()
    mock_instance.ping.assert_called_once()


def test_redis_service_verify_connection_failure(mock_redis):
    # Setup
    mock_instance = mock_redis.return_value
    mock_instance.ping.side_effect = redis.exceptions.AuthenticationError("Auth failed")

    # Execute
    # service = RedisService()

    # Assert
    mock_instance.ping.assert_called_once()
    # Should not raise exception because it's caught in _verify_connection


def test_get_cached_prompt_success(mock_redis):
    # Setup
    mock_instance = mock_redis.return_value
    mock_instance.get.return_value = "cached_value"
    service = RedisService()

    # Execute
    result = service.get_cached_prompt("test_key")

    # Assert
    assert result == "cached_value"
    mock_instance.get.assert_called_with("test_key")


def test_get_cached_prompt_error(mock_redis):
    # Setup
    mock_instance = mock_redis.return_value
    mock_instance.get.side_effect = Exception("Redis error")
    service = RedisService()

    # Execute
    result = service.get_cached_prompt("test_key")

    # Assert
    assert result is None
    mock_instance.get.assert_called_with("test_key")


def test_set_cached_prompt_success(mock_redis):
    # Setup
    mock_instance = mock_redis.return_value
    service = RedisService()

    # Execute
    service.set_cached_prompt("test_key", "test_value", 3600)

    # Assert
    mock_instance.setex.assert_called_with("test_key", 3600, "test_value")


def test_set_cached_prompt_error(mock_redis):
    # Setup
    mock_instance = mock_redis.return_value
    mock_instance.setex.side_effect = Exception("Redis error")
    service = RedisService()

    # Execute
    service.set_cached_prompt("test_key", "test_value")

    # Assert
    mock_instance.setex.assert_called()
