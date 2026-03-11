"""
Unit Tests — Preprocessing Worker
File: app/tests/test_worker.py

Run:
    pytest
"""

import json
import pytest
from unittest.mock import AsyncMock, patch


# ==========================================================
# decode_message()
# ==========================================================

from app.services.preprocessing_worker import decode_message


def test_decode_valid_json_string():
    data = {"data": json.dumps({"id": "p1"})}

    result = decode_message(data)

    assert result == {"id": "p1"}


def test_decode_invalid_json_string_returns_none():
    data = {"data": "{bad json"}

    result = decode_message(data)

    assert result is None


def test_decode_dict_passes_through():
    data = {"data": {"id": "p1"}}

    result = decode_message(data)

    assert result == {"id": "p1"}


def test_decode_missing_data_key_returns_original():
    data = {"id": "p1"}

    result = decode_message(data)

    assert result == data


# ==========================================================
# process_message()
# ==========================================================

@pytest.mark.asyncio
@patch("app.services.preprocessing_worker.finalize_message", new_callable=AsyncMock)
@patch("app.services.preprocessing_worker.preproc_stream")
@patch("app.services.preprocessing_worker.preprocessor")
async def test_process_message_success(
    mock_preprocessor,
    mock_preproc_stream,
    mock_finalize,
):
    """
    Happy path:
    - JSON decodes
    - preprocess returns data
    - save called
    - finalize called
    """

    mock_preprocessor.preprocess_post.return_value = {"id": "p1"}
    mock_preproc_stream.save = AsyncMock()

    from app.services.preprocessing_worker import process_message

    await process_message(
        "msg1",
        {"data": json.dumps({"id": "p1"})},
    )

    mock_preproc_stream.save.assert_called_once()
    mock_finalize.assert_called_once_with("msg1")


@pytest.mark.asyncio
@patch("app.services.preprocessing_worker.finalize_message", new_callable=AsyncMock)
async def test_process_message_invalid_json(mock_finalize):
    """
    Invalid JSON → should finalize immediately
    """

    from app.services.preprocessing_worker import process_message

    await process_message(
        "msg1",
        {"data": "{bad json"},
    )

    mock_finalize.assert_called_once_with("msg1")


@pytest.mark.asyncio
@patch("app.services.preprocessing_worker.finalize_message", new_callable=AsyncMock)
@patch("app.services.preprocessing_worker.preprocessor")
async def test_process_message_preprocess_returns_none(
    mock_preprocessor,
    mock_finalize,
):
    """
    Preprocessor returns None → should finalize without saving
    """

    mock_preprocessor.preprocess_post.return_value = None

    from app.services.preprocessing_worker import process_message

    await process_message(
        "msg1",
        {"data": json.dumps({"id": "p1"})},
    )

    mock_finalize.assert_called_once_with("msg1")


# ==========================================================
# recover_pending_messages()
# ==========================================================

@pytest.mark.asyncio
@patch("app.services.preprocessing_worker.process_message", new_callable=AsyncMock)
@patch("app.services.preprocessing_worker.source_stream")
async def test_recover_pending_messages_calls_process(
    mock_source_stream,
    mock_process,
):
    """
    Pending messages → process_message should be called
    """

    mock_source_stream.claim_pending = AsyncMock(
        return_value=[
            ("msg1", {"data": json.dumps({"id": "p1"})}),
            ("msg2", {"data": json.dumps({"id": "p2"})}),
        ]
    )

    from app.services.preprocessing_worker import recover_pending_messages

    await recover_pending_messages()

    assert mock_process.call_count == 2


@pytest.mark.asyncio
@patch("app.services.preprocessing_worker.source_stream")
async def test_recover_pending_messages_no_messages(mock_source_stream):
    """
    No pending messages → should exit safely
    """

    mock_source_stream.claim_pending = AsyncMock(return_value=[])

    from app.services.preprocessing_worker import recover_pending_messages

    await recover_pending_messages()


# ==========================================================
# cleanup_dead_consumers()
# ==========================================================

@pytest.mark.asyncio
@patch("app.services.preprocessing_worker.redis_client")
async def test_cleanup_dead_consumers_removes_idle(mock_redis):
    """
    Idle consumer with no pending messages → should be deleted
    """

    mock_redis.xinfo_consumers = AsyncMock(
        return_value=[
            {
                "name": "dead_consumer",
                "idle": 700000,  # > 10 minutes
                "pending": 0,
            }
        ]
    )

    from app.services.preprocessing_worker import cleanup_dead_consumers

    await cleanup_dead_consumers()

    mock_redis.xgroup_delconsumer.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.preprocessing_worker.redis_client")
async def test_cleanup_dead_consumers_keeps_active_consumer(mock_redis):
    """
    Current worker should never delete itself
    """

    mock_redis.xinfo_consumers = AsyncMock(
        return_value=[
            {
                "name": "preprocessing_worker_test",
                "idle": 100,
                "pending": 0,
            }
        ]
    )

    from app.services.preprocessing_worker import cleanup_dead_consumers

    await cleanup_dead_consumers()

    mock_redis.xgroup_delconsumer.assert_not_called()