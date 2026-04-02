"""
Unit Tests — Qdrant Vectorisation Worker
File: app/tests/test_vectorisation_worker.py

Run from qdrant-retrieval/:
    pytest
"""

import json
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Mock get_vector_strategy before the worker module is imported (it runs VectorisationService() at module level)
sys.modules.pop("app.services.qdrant_vectorisation_worker", None)
sys.modules.pop("app.services.vectorisation", None)
with patch("app.providers.vector.registry.get_vector_strategy") as _mock_strategy:
    _mock_strategy.return_value = MagicMock()
    from app.services.qdrant_vectorisation_worker import decode_message

from app.data.mock_reddit_payload import MOCK_REDDIT_PAYLOAD


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


# ─── finalize_message() ───────────────────────────────────────────────────────

@pytest.mark.asyncio
@patch("app.services.qdrant_vectorisation_worker.redis_client")
async def test_finalize_message_uses_pipeline(mock_redis):
    pipe_mock = MagicMock()
    pipe_mock.__aenter__ = AsyncMock(return_value=pipe_mock)
    pipe_mock.__aexit__ = AsyncMock(return_value=False)
    pipe_mock.xack = AsyncMock()
    pipe_mock.xdel = AsyncMock()
    pipe_mock.execute = AsyncMock()
    mock_redis.pipeline = MagicMock(return_value=pipe_mock)

    from app.services.qdrant_vectorisation_worker import finalize_message
    await finalize_message("msg_id_1")

    pipe_mock.xack.assert_called_once()
    pipe_mock.xdel.assert_called_once()
    pipe_mock.execute.assert_called_once()


# ─── send_heartbeat() ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
@patch("app.services.qdrant_vectorisation_worker.redis_client")
async def test_send_heartbeat_cancels_cleanly(mock_redis):
    import asyncio
    mock_redis.set = AsyncMock(side_effect=[None, asyncio.CancelledError()])

    from app.services.qdrant_vectorisation_worker import send_heartbeat
    with pytest.raises(asyncio.CancelledError):
        await send_heartbeat()


# ─── setup_consumer_group() ───────────────────────────────────────────────────

@pytest.mark.asyncio
@patch("app.services.qdrant_vectorisation_worker.sentiment_stream")
async def test_setup_consumer_group_success(mock_stream):
    mock_stream.create_consumer_group = AsyncMock(return_value=True)

    from app.services.qdrant_vectorisation_worker import setup_consumer_group
    await setup_consumer_group()

    mock_stream.create_consumer_group.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.qdrant_vectorisation_worker.sentiment_stream")
async def test_setup_consumer_group_already_exists(mock_stream):
    mock_stream.create_consumer_group = AsyncMock(side_effect=Exception("already exists"))

    from app.services.qdrant_vectorisation_worker import setup_consumer_group
    await setup_consumer_group()  # should not raise


# ─── cleanup_dead_consumers() ─────────────────────────────────────────────────

@pytest.mark.asyncio
@patch("app.services.qdrant_vectorisation_worker.CONSUMER_NAME", "active_consumer")
@patch("app.services.qdrant_vectorisation_worker.redis_client")
async def test_cleanup_removes_idle_consumer(mock_redis):
    mock_redis.xinfo_consumers = AsyncMock(return_value=[
        {"name": "dead_consumer", "idle": 700000, "pending": 0},
    ])
    mock_redis.xgroup_delconsumer = AsyncMock()

    from app.services.qdrant_vectorisation_worker import cleanup_dead_consumers
    await cleanup_dead_consumers()

    mock_redis.xgroup_delconsumer.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.qdrant_vectorisation_worker.CONSUMER_NAME", "active_consumer")
@patch("app.services.qdrant_vectorisation_worker.redis_client")
async def test_cleanup_keeps_active_consumer(mock_redis):
    mock_redis.xinfo_consumers = AsyncMock(return_value=[
        {"name": "active_consumer", "idle": 700000, "pending": 0},
    ])
    mock_redis.xgroup_delconsumer = AsyncMock()

    from app.services.qdrant_vectorisation_worker import cleanup_dead_consumers
    await cleanup_dead_consumers()

    mock_redis.xgroup_delconsumer.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.qdrant_vectorisation_worker.redis_client")
async def test_cleanup_exception_swallowed(mock_redis):
    mock_redis.xinfo_consumers = AsyncMock(side_effect=Exception("Redis error"))

    from app.services.qdrant_vectorisation_worker import cleanup_dead_consumers
    await cleanup_dead_consumers()  # should not raise


# ─── recover_pending_messages() ───────────────────────────────────────────────

@pytest.mark.asyncio
@patch("app.services.qdrant_vectorisation_worker.sentiment_stream")
async def test_recover_pending_no_messages(mock_stream):
    mock_stream.claim_pending = AsyncMock(return_value=[])

    from app.services.qdrant_vectorisation_worker import recover_pending_messages
    await recover_pending_messages()  # should not raise


# ─── process_message() ────────────────────────────────────────────────────────

def _make_pipe():
    pipe_mock = MagicMock()
    pipe_mock.__aenter__ = AsyncMock(return_value=pipe_mock)
    pipe_mock.__aexit__ = AsyncMock(return_value=False)
    pipe_mock.xack = AsyncMock()
    pipe_mock.xdel = AsyncMock()
    pipe_mock.execute = AsyncMock()
    return pipe_mock


@pytest.mark.asyncio
@patch("app.services.qdrant_vectorisation_worker.vector_service")
@patch("app.services.qdrant_vectorisation_worker.redis_client")
async def test_process_message_invalid_decode_skipped(mock_redis, mock_service):
    mock_redis.incr = AsyncMock()
    pipe_mock = _make_pipe()
    mock_redis.pipeline = MagicMock(return_value=pipe_mock)

    from app.services.qdrant_vectorisation_worker import process_message
    await process_message("msg_1", {"data": "{bad"})

    mock_redis.incr.assert_called_once()
    pipe_mock.xack.assert_called_once()
    mock_service.get_sanitised_news_payload.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.qdrant_vectorisation_worker.vector_service")
@patch("app.services.qdrant_vectorisation_worker.redis_client")
async def test_process_message_duplicate_skipped(mock_redis, mock_service):
    mock_redis.exists = AsyncMock(return_value=True)
    mock_redis.incr = AsyncMock()
    pipe_mock = _make_pipe()
    mock_redis.pipeline = MagicMock(return_value=pipe_mock)

    from app.services.qdrant_vectorisation_worker import process_message
    await process_message("msg_1", {"data": json.dumps({"id": "post_001"})})

    mock_redis.incr.assert_called_once()
    mock_service.get_sanitised_news_payload.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.qdrant_vectorisation_worker.vector_service")
@patch("app.services.qdrant_vectorisation_worker.redis_client")
async def test_process_message_already_processed_finalizes_only(mock_redis, mock_service):
    """qdrant_timestamp exists → finalize only, no vectorisation."""
    mock_redis.exists = AsyncMock(return_value=False)
    mock_redis.hget = AsyncMock(return_value="2026-01-01T10:00:00+08:00")
    mock_redis.incr = AsyncMock()
    pipe_mock = _make_pipe()
    mock_redis.pipeline = MagicMock(return_value=pipe_mock)

    from app.services.qdrant_vectorisation_worker import process_message
    await process_message("msg_1", {"data": json.dumps({"id": "post_001"})})

    pipe_mock.xack.assert_called_once()
    mock_service.get_sanitised_news_payload.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.qdrant_vectorisation_worker.aggregator_stream")
@patch("app.services.qdrant_vectorisation_worker.save_post")
@patch("app.services.qdrant_vectorisation_worker.mark_vectorised")
@patch("app.services.qdrant_vectorisation_worker.vector_service")
@patch("app.services.qdrant_vectorisation_worker.redis_client")
async def test_process_message_success(mock_redis, mock_service, mock_mark, mock_save, mock_agg):
    mock_redis.exists = AsyncMock(return_value=False)
    mock_redis.hget = AsyncMock(return_value=None)
    mock_redis.hset = AsyncMock()
    mock_redis.incr = AsyncMock()
    mock_save.return_value = None
    mock_mark.return_value = None
    mock_service.get_sanitised_news_payload = AsyncMock(return_value={"status": "success", "id": "vec_1"})
    mock_agg.save = AsyncMock(return_value="agg_id")
    pipe_mock = _make_pipe()
    mock_redis.pipeline = MagicMock(return_value=pipe_mock)

    from app.services.qdrant_vectorisation_worker import process_message
    await process_message("msg_1", {"data": json.dumps(MOCK_REDDIT_PAYLOAD["fields"])})

    mock_service.get_sanitised_news_payload.assert_called_once()
    mock_agg.save.assert_called_once()
    mock_redis.incr.assert_called_once()
    pipe_mock.xack.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.qdrant_vectorisation_worker.aggregator_stream")
@patch("app.services.qdrant_vectorisation_worker.save_post")
@patch("app.services.qdrant_vectorisation_worker.mark_vectorised")
@patch("app.services.qdrant_vectorisation_worker.vector_service")
@patch("app.services.qdrant_vectorisation_worker.redis_client")
async def test_process_message_vectorise_fails_removed(mock_redis, mock_service, mock_mark, mock_save, mock_agg):
    mock_redis.exists = AsyncMock(return_value=False)
    mock_redis.hget = AsyncMock(return_value=None)
    mock_redis.hset = AsyncMock()
    mock_redis.incr = AsyncMock()
    mock_save.return_value = None
    mock_service.get_sanitised_news_payload = AsyncMock(side_effect=Exception("Qdrant down"))
    pipe_mock = _make_pipe()
    mock_redis.pipeline = MagicMock(return_value=pipe_mock)

    from app.services.qdrant_vectorisation_worker import process_message
    await process_message("msg_1", {"data": json.dumps(MOCK_REDDIT_PAYLOAD["fields"])})

    mock_redis.incr.assert_called_once()
    mock_agg.save.assert_not_called()
    pipe_mock.xack.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.qdrant_vectorisation_worker.aggregator_stream")
@patch("app.services.qdrant_vectorisation_worker.save_post")
@patch("app.services.qdrant_vectorisation_worker.mark_vectorised")
@patch("app.services.qdrant_vectorisation_worker.vector_service")
@patch("app.services.qdrant_vectorisation_worker.redis_client")
async def test_process_message_postgres_error_continues(mock_redis, mock_service, mock_mark, mock_save, mock_agg):
    """Postgres save error → log and continue, still vectorise."""
    mock_redis.exists = AsyncMock(return_value=False)
    mock_redis.hget = AsyncMock(return_value=None)
    mock_redis.hset = AsyncMock()
    mock_redis.incr = AsyncMock()
    mock_save.side_effect = Exception("Postgres down")
    mock_mark.return_value = None
    mock_service.get_sanitised_news_payload = AsyncMock(return_value={"status": "success", "id": "vec_1"})
    mock_agg.save = AsyncMock(return_value="agg_id")
    pipe_mock = _make_pipe()
    mock_redis.pipeline = MagicMock(return_value=pipe_mock)

    from app.services.qdrant_vectorisation_worker import process_message
    await process_message("msg_1", {"data": json.dumps(MOCK_REDDIT_PAYLOAD["fields"])})

    mock_service.get_sanitised_news_payload.assert_called_once()
    mock_agg.save.assert_called_once()
    pipe_mock.xack.assert_called_once()
