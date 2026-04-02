"""
Unit Tests — Sentiment Analysis Worker
File: app/tests/test_worker.py

Run from sentiment-analysis-service/:
    pytest
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.sentiment_analysis_worker import decode_message


# ─── decode_message() ─────────────────────────────────────────────────────────

def test_decode_valid_json_string():
    data = {"data": json.dumps({"id": "p1", "content": {}})}
    assert decode_message(data) == {"id": "p1", "content": {}}


def test_decode_invalid_json_string_returns_none():
    data = {"data": "{bad json"}
    assert decode_message(data) is None


def test_decode_dict_passes_through():
    data = {"data": {"id": "p1"}}
    assert decode_message(data) == {"id": "p1"}


def test_decode_missing_data_key_returns_original():
    data = {"id": "p1"}
    assert decode_message(data) == data


# ─── process_message() ────────────────────────────────────────────────────────

def _make_sentiment_service(result=None):
    svc = MagicMock()
    svc.analyse = AsyncMock(return_value=result)
    return svc


@pytest.mark.asyncio
@patch("app.services.sentiment_analysis_worker.sentiment_stream")
@patch("app.services.sentiment_analysis_worker.sentiment_service")
@patch("app.services.sentiment_analysis_worker.redis_client")
async def test_process_message_invalid_decode_skipped(mock_redis, mock_svc, mock_stream):
    """Malformed message → skip, increment counter, finalize."""
    mock_redis.incr = AsyncMock()
    pipe_mock = MagicMock()
    pipe_mock.__aenter__ = AsyncMock(return_value=pipe_mock)
    pipe_mock.__aexit__ = AsyncMock(return_value=False)
    pipe_mock.xack = AsyncMock()
    pipe_mock.xdel = AsyncMock()
    pipe_mock.execute = AsyncMock()
    mock_redis.pipeline = MagicMock(return_value=pipe_mock)

    from app.services.sentiment_analysis_worker import process_message
    await process_message("msg_1", {"data": "{bad"})

    mock_redis.incr.assert_called_once()
    pipe_mock.xack.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.sentiment_analysis_worker.sentiment_stream")
@patch("app.services.sentiment_analysis_worker.sentiment_service")
@patch("app.services.sentiment_analysis_worker.redis_client")
async def test_process_message_duplicate_skipped(mock_redis, mock_svc, mock_stream):
    """Duplicate post → increment dup counter, finalize, no analysis."""
    mock_redis.exists = AsyncMock(return_value=True)
    mock_redis.incr = AsyncMock()
    mock_redis.hset = AsyncMock()
    pipe_mock = MagicMock()
    pipe_mock.__aenter__ = AsyncMock(return_value=pipe_mock)
    pipe_mock.__aexit__ = AsyncMock(return_value=False)
    pipe_mock.xack = AsyncMock()
    pipe_mock.xdel = AsyncMock()
    pipe_mock.execute = AsyncMock()
    mock_redis.pipeline = MagicMock(return_value=pipe_mock)

    from app.services.sentiment_analysis_worker import process_message
    data = {"data": json.dumps({"id": "post_001"})}
    await process_message("msg_1", data)

    mock_redis.incr.assert_called_once()
    mock_svc.analyse.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.sentiment_analysis_worker.sentiment_stream")
@patch("app.services.sentiment_analysis_worker.sentiment_service")
@patch("app.services.sentiment_analysis_worker.redis_client")
async def test_process_message_success_saves_to_stream(mock_redis, mock_svc, mock_stream):
    """Valid new post → analysed and saved to sentiment stream."""
    mock_redis.exists = AsyncMock(return_value=False)
    mock_redis.hset = AsyncMock()
    mock_redis.incr = AsyncMock()

    sentiment_result = {
        "id": "post_001",
        "sentiment_analysis": {"analysis_successful": True, "reasoning": ""},
    }
    mock_svc.analyse = AsyncMock(return_value=sentiment_result)
    mock_stream.save = AsyncMock(return_value="stream_id_1")

    pipe_mock = MagicMock()
    pipe_mock.__aenter__ = AsyncMock(return_value=pipe_mock)
    pipe_mock.__aexit__ = AsyncMock(return_value=False)
    pipe_mock.xack = AsyncMock()
    pipe_mock.xdel = AsyncMock()
    pipe_mock.execute = AsyncMock()
    mock_redis.pipeline = MagicMock(return_value=pipe_mock)

    from app.services.sentiment_analysis_worker import process_message
    data = {"data": json.dumps({"id": "post_001", "content": {}})}
    await process_message("msg_1", data)

    mock_svc.analyse.assert_called_once()
    mock_stream.save.assert_called_once()
    pipe_mock.xack.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.sentiment_analysis_worker.sentiment_stream")
@patch("app.services.sentiment_analysis_worker.sentiment_service")
@patch("app.services.sentiment_analysis_worker.redis_client")
async def test_process_message_analysis_failed_reasoning_skips_save(mock_redis, mock_svc, mock_stream):
    """'Analysis failed' in reasoning → skip save, increment removed counter."""
    mock_redis.exists = AsyncMock(return_value=False)
    mock_redis.hset = AsyncMock()
    mock_redis.incr = AsyncMock()

    sentiment_result = {
        "id": "post_002",
        "sentiment_analysis": {"analysis_successful": False, "reasoning": "Analysis failed"},
    }
    mock_svc.analyse = AsyncMock(return_value=sentiment_result)

    pipe_mock = MagicMock()
    pipe_mock.__aenter__ = AsyncMock(return_value=pipe_mock)
    pipe_mock.__aexit__ = AsyncMock(return_value=False)
    pipe_mock.xack = AsyncMock()
    pipe_mock.xdel = AsyncMock()
    pipe_mock.execute = AsyncMock()
    mock_redis.pipeline = MagicMock(return_value=pipe_mock)

    from app.services.sentiment_analysis_worker import process_message
    data = {"data": json.dumps({"id": "post_002"})}
    await process_message("msg_1", data)

    mock_redis.incr.assert_called_once()
    mock_stream.save.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.sentiment_analysis_worker.sentiment_stream")
@patch("app.services.sentiment_analysis_worker.sentiment_service")
@patch("app.services.sentiment_analysis_worker.redis_client")
async def test_process_message_null_result_skips_save(mock_redis, mock_svc, mock_stream):
    """analyse() returns None → skip save, increment removed counter."""
    mock_redis.exists = AsyncMock(return_value=False)
    mock_redis.hset = AsyncMock()
    mock_redis.incr = AsyncMock()
    mock_svc.analyse = AsyncMock(return_value=None)

    pipe_mock = MagicMock()
    pipe_mock.__aenter__ = AsyncMock(return_value=pipe_mock)
    pipe_mock.__aexit__ = AsyncMock(return_value=False)
    pipe_mock.xack = AsyncMock()
    pipe_mock.xdel = AsyncMock()
    pipe_mock.execute = AsyncMock()
    mock_redis.pipeline = MagicMock(return_value=pipe_mock)

    from app.services.sentiment_analysis_worker import process_message
    data = {"data": json.dumps({"id": "post_003"})}
    await process_message("msg_1", data)

    mock_redis.incr.assert_called_once()
    mock_stream.save.assert_not_called()


# ─── finalize_message() ───────────────────────────────────────────────────────

@pytest.mark.asyncio
@patch("app.services.sentiment_analysis_worker.redis_client")
async def test_finalize_message_uses_pipeline(mock_redis):
    """finalize_message → pipeline xack + xdel + execute called."""
    pipe_mock = MagicMock()
    pipe_mock.__aenter__ = AsyncMock(return_value=pipe_mock)
    pipe_mock.__aexit__ = AsyncMock(return_value=False)
    pipe_mock.xack = AsyncMock()
    pipe_mock.xdel = AsyncMock()
    pipe_mock.execute = AsyncMock()
    mock_redis.pipeline = MagicMock(return_value=pipe_mock)

    from app.services.sentiment_analysis_worker import finalize_message
    await finalize_message("msg_id_1")

    pipe_mock.xack.assert_called_once()
    pipe_mock.xdel.assert_called_once()
    pipe_mock.execute.assert_called_once()


# ─── send_heartbeat() ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
@patch("app.services.sentiment_analysis_worker.redis_client")
async def test_send_heartbeat_cancels_cleanly(mock_redis):
    """CancelledError in heartbeat loop → re-raised cleanly."""
    import asyncio
    mock_redis.set = AsyncMock(side_effect=[None, asyncio.CancelledError()])

    from app.services.sentiment_analysis_worker import send_heartbeat
    with pytest.raises(asyncio.CancelledError):
        await send_heartbeat()


# ─── setup_consumer_group() ───────────────────────────────────────────────────

@pytest.mark.asyncio
@patch("app.services.sentiment_analysis_worker.event_stream")
async def test_setup_consumer_group_success(mock_stream):
    """Consumer group created successfully."""
    mock_stream.create_consumer_group = AsyncMock(return_value=True)

    from app.services.sentiment_analysis_worker import setup_consumer_group
    await setup_consumer_group()

    mock_stream.create_consumer_group.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.sentiment_analysis_worker.event_stream")
async def test_setup_consumer_group_already_exists(mock_stream):
    """Exception during group creation (already exists) → swallowed."""
    mock_stream.create_consumer_group = AsyncMock(side_effect=Exception("already exists"))

    from app.services.sentiment_analysis_worker import setup_consumer_group
    await setup_consumer_group()  # should not raise


# ─── recover_pending_messages() ───────────────────────────────────────────────

@pytest.mark.asyncio
@patch("app.services.sentiment_analysis_worker.event_stream")
async def test_recover_pending_no_messages(mock_stream):
    """No pending messages → nothing processed."""
    mock_stream.claim_pending = AsyncMock(return_value=[])

    from app.services.sentiment_analysis_worker import recover_pending_messages
    await recover_pending_messages()  # should not raise


@pytest.mark.asyncio
@patch("app.services.sentiment_analysis_worker.sentiment_stream")
@patch("app.services.sentiment_analysis_worker.sentiment_service")
@patch("app.services.sentiment_analysis_worker.redis_client")
@patch("app.services.sentiment_analysis_worker.event_stream")
async def test_recover_pending_processes_claimed(mock_event_stream, mock_redis, mock_svc, mock_sentiment_stream):
    """Claimed messages → process_message called for each."""
    mock_event_stream.claim_pending = AsyncMock(return_value=[
        ("msg_1", {"data": json.dumps({"id": "p1"})}),
    ])
    mock_redis.exists = AsyncMock(return_value=False)
    mock_redis.hset = AsyncMock()
    mock_redis.incr = AsyncMock()

    sentiment_result = {"id": "p1", "sentiment_analysis": {"analysis_successful": True, "reasoning": ""}}
    mock_svc.analyse = AsyncMock(return_value=sentiment_result)
    mock_sentiment_stream.save = AsyncMock()

    pipe_mock = MagicMock()
    pipe_mock.__aenter__ = AsyncMock(return_value=pipe_mock)
    pipe_mock.__aexit__ = AsyncMock(return_value=False)
    pipe_mock.xack = AsyncMock()
    pipe_mock.xdel = AsyncMock()
    pipe_mock.execute = AsyncMock()
    mock_redis.pipeline = MagicMock(return_value=pipe_mock)

    from app.services.sentiment_analysis_worker import recover_pending_messages
    await recover_pending_messages()

    mock_svc.analyse.assert_called_once()


# ─── cleanup_dead_consumers() ─────────────────────────────────────────────────

@pytest.mark.asyncio
@patch("app.services.sentiment_analysis_worker.CONSUMER_NAME", "active_consumer")
@patch("app.services.sentiment_analysis_worker.redis_client")
async def test_cleanup_dead_consumers_removes_idle(mock_redis):
    """Consumer with idle > threshold and 0 pending → deleted."""
    mock_redis.xinfo_consumers = AsyncMock(return_value=[
        {"name": "dead_consumer", "idle": 700000, "pending": 0},
    ])
    mock_redis.xgroup_delconsumer = AsyncMock()

    from app.services.sentiment_analysis_worker import cleanup_dead_consumers
    await cleanup_dead_consumers()

    mock_redis.xgroup_delconsumer.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.sentiment_analysis_worker.CONSUMER_NAME", "active_consumer")
@patch("app.services.sentiment_analysis_worker.redis_client")
async def test_cleanup_dead_consumers_keeps_active(mock_redis):
    """Consumer matching CONSUMER_NAME → not deleted."""
    mock_redis.xinfo_consumers = AsyncMock(return_value=[
        {"name": "active_consumer", "idle": 700000, "pending": 0},
    ])
    mock_redis.xgroup_delconsumer = AsyncMock()

    from app.services.sentiment_analysis_worker import cleanup_dead_consumers
    await cleanup_dead_consumers()

    mock_redis.xgroup_delconsumer.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.sentiment_analysis_worker.redis_client")
async def test_cleanup_dead_consumers_exception_swallowed(mock_redis):
    """xinfo_consumers raises → error swallowed gracefully."""
    mock_redis.xinfo_consumers = AsyncMock(side_effect=Exception("Redis error"))

    from app.services.sentiment_analysis_worker import cleanup_dead_consumers
    await cleanup_dead_consumers()  # should not raise
