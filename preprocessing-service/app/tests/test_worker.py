"""
Unit Tests — Preprocessing Worker
File: app/tests/test_worker.py

Run:
    pytest
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


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
@patch("app.services.preprocessing_worker.redis_client")
async def test_process_message_success(
    mock_redis,
    mock_preprocessor,
    mock_preproc_stream,
    mock_finalize,
):
    """Happy path: decodes → not duplicate → preprocesses → saves → finalizes."""
    mock_redis.exists = AsyncMock(return_value=False)
    mock_redis.hget = AsyncMock(return_value=None)
    mock_redis.hset = AsyncMock()
    mock_redis.incr = AsyncMock()
    mock_preprocessor.preprocess_post.return_value = {"id": "p1"}
    mock_preproc_stream.save = AsyncMock()

    from app.services.preprocessing_worker import process_message

    await process_message("msg1", {"data": json.dumps({"id": "p1"})})

    mock_preproc_stream.save.assert_called_once()
    mock_finalize.assert_called_once_with("msg1")


@pytest.mark.asyncio
@patch("app.services.preprocessing_worker.finalize_message", new_callable=AsyncMock)
@patch("app.services.preprocessing_worker.redis_client")
async def test_process_message_invalid_json(mock_redis, mock_finalize):
    """Invalid JSON → increments removed counter, finalizes immediately."""
    mock_redis.incr = AsyncMock()

    from app.services.preprocessing_worker import process_message

    await process_message("msg1", {"data": "{bad json"})

    mock_redis.incr.assert_called_once()
    mock_finalize.assert_called_once_with("msg1")


@pytest.mark.asyncio
@patch("app.services.preprocessing_worker.finalize_message", new_callable=AsyncMock)
@patch("app.services.preprocessing_worker.preprocessor")
@patch("app.services.preprocessing_worker.redis_client")
async def test_process_message_preprocess_returns_none(
    mock_redis,
    mock_preprocessor,
    mock_finalize,
):
    """Preprocessor returns None → increments removed counter, finalizes without saving."""
    mock_redis.exists = AsyncMock(return_value=False)
    mock_redis.hget = AsyncMock(return_value=None)
    mock_redis.hset = AsyncMock()
    mock_redis.incr = AsyncMock()
    mock_preprocessor.preprocess_post.return_value = None

    from app.services.preprocessing_worker import process_message

    await process_message("msg1", {"data": json.dumps({"id": "p1"})})

    mock_redis.incr.assert_called_once()
    mock_finalize.assert_called_once_with("msg1")


@pytest.mark.asyncio
@patch("app.services.preprocessing_worker.finalize_message", new_callable=AsyncMock)
@patch("app.services.preprocessing_worker.redis_client")
async def test_process_message_duplicate_skipped(mock_redis, mock_finalize):
    """Duplicate post → increments dup counter, finalizes without preprocessing."""
    mock_redis.exists = AsyncMock(return_value=True)
    mock_redis.incr = AsyncMock()

    from app.services.preprocessing_worker import process_message

    await process_message("msg1", {"data": json.dumps({"id": "p1"})})

    mock_redis.incr.assert_called_once()
    mock_finalize.assert_called_once_with("msg1")


@pytest.mark.asyncio
@patch("app.services.preprocessing_worker.finalize_message", new_callable=AsyncMock)
@patch("app.services.preprocessing_worker.preproc_stream")
@patch("app.services.preprocessing_worker.preprocessor")
@patch("app.services.preprocessing_worker.redis_client")
async def test_process_message_timestamps_written(
    mock_redis,
    mock_preprocessor,
    mock_preproc_stream,
    _mock_finalize,
):
    """Both start and end timestamps are written to Redis for a successful post."""
    mock_redis.exists = AsyncMock(return_value=False)
    mock_redis.hget = AsyncMock(return_value=None)
    mock_redis.hset = AsyncMock()
    mock_redis.incr = AsyncMock()
    mock_preprocessor.preprocess_post.return_value = {"id": "p1"}
    mock_preproc_stream.save = AsyncMock()

    from app.services.preprocessing_worker import process_message

    await process_message("msg1", {"data": json.dumps({"id": "p1"})})

    assert mock_redis.hset.call_count == 2
    calls = [call.args[1] for call in mock_redis.hset.call_args_list]
    assert "preproc_timestamp_start" in calls
    assert "preproc_timestamp" in calls


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
    """Pending messages → process_message called for each."""
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
    """No pending messages → exits safely without calling process_message."""
    mock_source_stream.claim_pending = AsyncMock(return_value=[])

    from app.services.preprocessing_worker import recover_pending_messages

    await recover_pending_messages()


# ==========================================================
# cleanup_dead_consumers()
# ==========================================================

@pytest.mark.asyncio
@patch("app.services.preprocessing_worker.redis_client")
async def test_cleanup_dead_consumers_removes_idle(mock_redis):
    """Consumer idle > 10 min with 0 pending → deleted."""
    mock_redis.xinfo_consumers = AsyncMock(
        return_value=[
            {
                "name": "dead_consumer",
                "idle": 700000,  # > 10 minutes in ms
                "pending": 0,
            }
        ]
    )
    mock_redis.xgroup_delconsumer = AsyncMock()

    from app.services.preprocessing_worker import cleanup_dead_consumers

    await cleanup_dead_consumers()

    mock_redis.xgroup_delconsumer.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.preprocessing_worker.redis_client")
async def test_cleanup_dead_consumers_keeps_consumer_with_pending(mock_redis):
    """Idle consumer that still has pending messages → not deleted."""
    mock_redis.xinfo_consumers = AsyncMock(
        return_value=[
            {
                "name": "busy_consumer",
                "idle": 700000,
                "pending": 3,  # has pending — must not delete
            }
        ]
    )
    mock_redis.xgroup_delconsumer = AsyncMock()

    from app.services.preprocessing_worker import cleanup_dead_consumers

    await cleanup_dead_consumers()

    mock_redis.xgroup_delconsumer.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.preprocessing_worker.CONSUMER_NAME", "preprocessing_worker_abc123")
@patch("app.services.preprocessing_worker.redis_client")
async def test_cleanup_dead_consumers_never_deletes_self(mock_redis):
    """Worker never deletes its own consumer entry, even if idle."""
    mock_redis.xinfo_consumers = AsyncMock(
        return_value=[
            {
                "name": "preprocessing_worker_abc123",  # same as CONSUMER_NAME
                "idle": 700000,
                "pending": 0,
            }
        ]
    )
    mock_redis.xgroup_delconsumer = AsyncMock()

    from app.services.preprocessing_worker import cleanup_dead_consumers

    await cleanup_dead_consumers()

    mock_redis.xgroup_delconsumer.assert_not_called()


# ==========================================================
# setup_consumer_group()
# ==========================================================

@pytest.mark.asyncio
@patch("app.services.preprocessing_worker.source_stream")
async def test_setup_consumer_group_success(mock_source_stream):
    """Consumer group created successfully → create_consumer_group called once."""
    mock_source_stream.create_consumer_group = AsyncMock()

    from app.services.preprocessing_worker import setup_consumer_group

    await setup_consumer_group()

    mock_source_stream.create_consumer_group.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.preprocessing_worker.source_stream")
async def test_setup_consumer_group_already_exists_swallowed(mock_source_stream):
    """Exception from create_consumer_group (e.g. already exists) → swallowed, no raise."""
    mock_source_stream.create_consumer_group = AsyncMock(
        side_effect=Exception("BUSYGROUP already exists")
    )

    from app.services.preprocessing_worker import setup_consumer_group

    await setup_consumer_group()  # should not raise


# ==========================================================
# finalize_message()
# ==========================================================

@pytest.mark.asyncio
@patch("app.services.preprocessing_worker.redis_client")
async def test_finalize_message_pipeline(mock_redis):
    """finalize_message uses pipeline to XACK and XDEL atomically."""
    pipe_mock = AsyncMock()
    pipe_mock.__aenter__ = AsyncMock(return_value=pipe_mock)
    pipe_mock.__aexit__ = AsyncMock(return_value=False)
    mock_redis.pipeline = MagicMock(return_value=pipe_mock)

    from app.services.preprocessing_worker import finalize_message

    await finalize_message("msg_id_1")

    pipe_mock.xack.assert_called_once()
    pipe_mock.xdel.assert_called_once()
    pipe_mock.execute.assert_called_once()


# ==========================================================
# send_heartbeat()
# ==========================================================

@pytest.mark.asyncio
@patch("app.services.preprocessing_worker.redis_client")
async def test_send_heartbeat_cancelled(mock_redis):
    """CancelledError from asyncio.sleep → re-raised after logging."""
    mock_redis.set = AsyncMock()

    with patch("asyncio.sleep", side_effect=asyncio.CancelledError):
        from app.services.preprocessing_worker import send_heartbeat

        with pytest.raises(asyncio.CancelledError):
            await send_heartbeat()

    mock_redis.set.assert_called_once()


# ==========================================================
# recover_pending_messages() — exception branch
# ==========================================================

@pytest.mark.asyncio
@patch("app.services.preprocessing_worker.process_message", new_callable=AsyncMock)
@patch("app.services.preprocessing_worker.source_stream")
async def test_recover_pending_logs_exceptions(mock_source_stream, mock_process):
    """process_message raises → exception captured by gather, logged, not re-raised."""
    mock_source_stream.claim_pending = AsyncMock(
        return_value=[("msg1", {"data": json.dumps({"id": "p1"})})]
    )
    mock_process.side_effect = Exception("processing blew up")

    from app.services.preprocessing_worker import recover_pending_messages

    await recover_pending_messages()  # should not raise


# ==========================================================
# cleanup_dead_consumers() — exception branch
# ==========================================================

@pytest.mark.asyncio
@patch("app.services.preprocessing_worker.redis_client")
async def test_cleanup_dead_consumers_exception_swallowed(mock_redis):
    """xinfo_consumers raises → exception swallowed, no re-raise."""
    mock_redis.xinfo_consumers = AsyncMock(side_effect=Exception("Redis down"))

    from app.services.preprocessing_worker import cleanup_dead_consumers

    await cleanup_dead_consumers()  # should not raise


# ==========================================================
# process_message() — CancelledError from save re-raised
# ==========================================================

@pytest.mark.asyncio
@patch("app.services.preprocessing_worker.finalize_message", new_callable=AsyncMock)
@patch("app.services.preprocessing_worker.preproc_stream")
@patch("app.services.preprocessing_worker.preprocessor")
@patch("app.services.preprocessing_worker.redis_client")
async def test_process_message_cancelled_error_reraises(
    mock_redis,
    mock_preprocessor,
    mock_preproc_stream,
    _mock_finalize,
):
    """CancelledError from preproc_stream.save → re-raised (not swallowed)."""
    mock_redis.exists = AsyncMock(return_value=False)
    mock_redis.hget = AsyncMock(return_value=None)
    mock_redis.hset = AsyncMock()
    mock_redis.incr = AsyncMock()
    mock_preprocessor.preprocess_post.return_value = {"id": "p1"}
    mock_preproc_stream.save = AsyncMock(side_effect=asyncio.CancelledError)

    from app.services.preprocessing_worker import process_message

    with pytest.raises(asyncio.CancelledError):
        await process_message("msg1", {"data": json.dumps({"id": "p1"})})
