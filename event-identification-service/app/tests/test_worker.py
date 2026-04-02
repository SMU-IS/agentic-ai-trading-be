"""
Unit Tests — Event Identification Worker

All Redis, bucket, and LLM calls are mocked.
No real connections made.
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ==========================================================
# decode_message()
# ==========================================================

from app.services.event_identification_worker import decode_message


def test_decode_valid_json_string():
    data = {"data": json.dumps({"id": "p1"})}
    assert decode_message(data) == {"id": "p1"}


def test_decode_invalid_json_string_returns_none():
    data = {"data": "{bad json"}
    assert decode_message(data) is None


def test_decode_dict_passes_through():
    data = {"data": {"id": "p1"}}
    assert decode_message(data) == {"id": "p1"}


def test_decode_missing_data_key_returns_original():
    data = {"id": "p1"}
    assert decode_message(data) == data


# ==========================================================
# process_message()
# ==========================================================

def _make_event_service(result=None, neweventcount=0):
    svc = MagicMock()
    svc.analyse_event = AsyncMock(return_value=result)
    svc.neweventcount = neweventcount
    return svc


@pytest.mark.asyncio
@patch("app.services.event_identification_worker.finalize_message", new_callable=AsyncMock)
@patch("app.services.event_identification_worker.event_stream")
@patch("app.services.event_identification_worker.update_event_list_in_redis", new_callable=AsyncMock)
@patch("app.services.event_identification_worker.redis_client")
async def test_process_message_success(mock_redis, mock_update, mock_event_stream, mock_finalize):
    """Happy path: decodes → not dup → event found → saves → finalizes."""
    mock_redis.exists = AsyncMock(return_value=False)
    mock_redis.hset = AsyncMock()
    mock_redis.incr = AsyncMock()
    mock_event_stream.save = AsyncMock()

    svc = _make_event_service({
        "id": "p1",
        "ticker_metadata": {"AAPL": {"event_type": "earnings"}},
        "metadata": {"ticker": None},
    })

    from app.services.event_identification_worker import process_message
    await process_message("msg1", {"data": json.dumps({"id": "p1"})}, event_service=svc)

    mock_event_stream.save.assert_called_once()
    mock_finalize.assert_called_once_with("msg1")


@pytest.mark.asyncio
@patch("app.services.event_identification_worker.finalize_message", new_callable=AsyncMock)
@patch("app.services.event_identification_worker.redis_client")
async def test_process_message_invalid_json(mock_redis, mock_finalize):
    """Invalid JSON → increments removed counter, finalizes immediately."""
    mock_redis.incr = AsyncMock()

    from app.services.event_identification_worker import process_message
    await process_message("msg1", {"data": "{bad json"}, event_service=MagicMock())

    mock_redis.incr.assert_called_once()
    mock_finalize.assert_called_once_with("msg1")


@pytest.mark.asyncio
@patch("app.services.event_identification_worker.finalize_message", new_callable=AsyncMock)
@patch("app.services.event_identification_worker.redis_client")
async def test_process_message_duplicate_skipped(mock_redis, mock_finalize):
    """Duplicate post → increments dup counter, finalizes without processing."""
    mock_redis.exists = AsyncMock(return_value=True)
    mock_redis.incr = AsyncMock()

    from app.services.event_identification_worker import process_message
    await process_message("msg1", {"data": json.dumps({"id": "p1"})}, event_service=MagicMock())

    mock_redis.incr.assert_called_once()
    mock_finalize.assert_called_once_with("msg1")


@pytest.mark.asyncio
@patch("app.services.event_identification_worker.finalize_message", new_callable=AsyncMock)
@patch("app.services.event_identification_worker.redis_client")
async def test_process_message_event_service_returns_none(mock_redis, mock_finalize):
    """analyse_event returns None → increments removed counter, finalizes."""
    mock_redis.exists = AsyncMock(return_value=False)
    mock_redis.hset = AsyncMock()
    mock_redis.incr = AsyncMock()

    from app.services.event_identification_worker import process_message
    await process_message("msg1", {"data": json.dumps({"id": "p1"})}, event_service=_make_event_service(None))

    mock_redis.incr.assert_called_once()
    mock_finalize.assert_called_once_with("msg1")


@pytest.mark.asyncio
@patch("app.services.event_identification_worker.finalize_message", new_callable=AsyncMock)
@patch("app.services.event_identification_worker.redis_client")
async def test_process_message_no_event_type_filtered(mock_redis, mock_finalize):
    """ticker_metadata has entry with no event_type → filtered, post removed."""
    mock_redis.exists = AsyncMock(return_value=False)
    mock_redis.hset = AsyncMock()
    mock_redis.incr = AsyncMock()

    svc = _make_event_service({
        "id": "p1",
        "ticker_metadata": {"AAPL": {"event_type": None}},
        "metadata": {},
    })

    from app.services.event_identification_worker import process_message
    await process_message("msg1", {"data": json.dumps({"id": "p1"})}, event_service=svc)

    mock_redis.incr.assert_called_once()
    mock_finalize.assert_called_once_with("msg1")


@pytest.mark.asyncio
@patch("app.services.event_identification_worker.finalize_message", new_callable=AsyncMock)
@patch("app.services.event_identification_worker.event_stream")
@patch("app.services.event_identification_worker.update_event_list_in_redis", new_callable=AsyncMock)
@patch("app.services.event_identification_worker.redis_client")
async def test_process_message_timestamps_written(mock_redis, mock_update, mock_event_stream, _mock_finalize):
    """Both start and end timestamps written for a successful post."""
    mock_redis.exists = AsyncMock(return_value=False)
    mock_redis.hset = AsyncMock()
    mock_redis.incr = AsyncMock()
    mock_event_stream.save = AsyncMock()

    svc = _make_event_service({
        "id": "p1",
        "ticker_metadata": {"AAPL": {"event_type": "earnings"}},
        "metadata": {"ticker": None},
    })

    from app.services.event_identification_worker import process_message
    await process_message("msg1", {"data": json.dumps({"id": "p1"})}, event_service=svc)

    assert mock_redis.hset.call_count == 2
    fields = [call.args[1] for call in mock_redis.hset.call_args_list]
    assert "event_timestamp_start" in fields
    assert "event_timestamp" in fields


@pytest.mark.asyncio
@patch("app.services.event_identification_worker.finalize_message", new_callable=AsyncMock)
@patch("app.services.event_identification_worker.event_stream")
@patch("app.services.event_identification_worker.update_event_list_in_redis", new_callable=AsyncMock)
@patch("app.services.event_identification_worker.redis_client")
async def test_process_message_cancelled_error_reraises(mock_redis, mock_update, mock_event_stream, _mock_finalize):
    """CancelledError from event_stream.save → re-raised."""
    mock_redis.exists = AsyncMock(return_value=False)
    mock_redis.hset = AsyncMock()
    mock_redis.incr = AsyncMock()
    mock_event_stream.save = AsyncMock(side_effect=asyncio.CancelledError)

    svc = _make_event_service({
        "id": "p1",
        "ticker_metadata": {"AAPL": {"event_type": "earnings"}},
        "metadata": {"ticker": None},
    })

    from app.services.event_identification_worker import process_message
    with pytest.raises(asyncio.CancelledError):
        await process_message("msg1", {"data": json.dumps({"id": "p1"})}, event_service=svc)


# ==========================================================
# setup_consumer_group()
# ==========================================================

@pytest.mark.asyncio
@patch("app.services.event_identification_worker.ticker_stream")
async def test_setup_consumer_group_success(mock_ticker_stream):
    mock_ticker_stream.create_consumer_group = AsyncMock()

    from app.services.event_identification_worker import setup_consumer_group
    await setup_consumer_group()

    mock_ticker_stream.create_consumer_group.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.event_identification_worker.ticker_stream")
async def test_setup_consumer_group_exception_swallowed(mock_ticker_stream):
    mock_ticker_stream.create_consumer_group = AsyncMock(side_effect=Exception("BUSYGROUP"))

    from app.services.event_identification_worker import setup_consumer_group
    await setup_consumer_group()  # should not raise


# ==========================================================
# finalize_message()
# ==========================================================

@pytest.mark.asyncio
@patch("app.services.event_identification_worker.redis_client")
async def test_finalize_message_pipeline(mock_redis):
    """finalize_message uses pipeline to XACK + XDEL atomically."""
    pipe_mock = AsyncMock()
    pipe_mock.__aenter__ = AsyncMock(return_value=pipe_mock)
    pipe_mock.__aexit__ = AsyncMock(return_value=False)
    mock_redis.pipeline = MagicMock(return_value=pipe_mock)

    from app.services.event_identification_worker import finalize_message
    await finalize_message("msg_id_1")

    pipe_mock.xack.assert_called_once()
    pipe_mock.xdel.assert_called_once()
    pipe_mock.execute.assert_called_once()


# ==========================================================
# send_heartbeat()
# ==========================================================

@pytest.mark.asyncio
@patch("app.services.event_identification_worker.redis_client")
async def test_send_heartbeat_cancelled(mock_redis):
    """CancelledError from asyncio.sleep → re-raised."""
    mock_redis.set = AsyncMock()

    with patch("asyncio.sleep", side_effect=asyncio.CancelledError):
        from app.services.event_identification_worker import send_heartbeat
        with pytest.raises(asyncio.CancelledError):
            await send_heartbeat()

    mock_redis.set.assert_called_once()


# ==========================================================
# load_event_list()
# ==========================================================

@pytest.mark.asyncio
@patch("app.services.event_identification_worker.redis_client")
async def test_load_event_list_from_redis(mock_redis):
    """Data in Redis → returned directly, bucket not called."""
    mock_redis.get = AsyncMock(return_value='{"EARNINGS": {}}')

    from app.services.event_identification_worker import load_event_list
    result = await load_event_list()

    assert result == {"EARNINGS": {}}
    mock_redis.set.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.event_identification_worker.redis_client")
async def test_load_event_list_falls_back_to_bucket(mock_redis):
    """Redis empty → loads from bucket, caches, returns parsed data."""
    import app.services.event_identification_worker as worker_mod

    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock()
    worker_mod.bucket.read_text = MagicMock(return_value='{"MERGER": {}}')

    from app.services.event_identification_worker import load_event_list
    result = await load_event_list()

    assert result == {"MERGER": {}}
    mock_redis.set.assert_called_once()


# ==========================================================
# update_event_list_in_redis()
# ==========================================================

@pytest.mark.asyncio
@patch("app.services.event_identification_worker.redis_client")
async def test_update_event_list_skips_when_no_new_events(mock_redis):
    """neweventcount <= 0 → returns immediately without acquiring lock."""
    mock_redis.lock = MagicMock()

    svc = MagicMock()
    svc.neweventcount = 0

    from app.services.event_identification_worker import update_event_list_in_redis
    await update_event_list_in_redis(svc)

    mock_redis.lock.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.event_identification_worker._last_event_list_update", 0.0)
@patch("app.services.event_identification_worker.redis_client")
async def test_update_event_list_merges_and_saves(mock_redis):
    """New events present → acquires lock, merges with existing, writes to Redis."""
    lock_mock = AsyncMock()
    lock_mock.__aenter__ = AsyncMock(return_value=lock_mock)
    lock_mock.__aexit__ = AsyncMock(return_value=False)
    mock_redis.lock = MagicMock(return_value=lock_mock)
    mock_redis.get = AsyncMock(return_value='{"EXISTING": {}}')
    mock_redis.set = AsyncMock()

    svc = MagicMock()
    svc.neweventcount = 1
    svc.event_list = {"NEW_EVENT": {}}

    from app.services.event_identification_worker import update_event_list_in_redis
    await update_event_list_in_redis(svc)

    mock_redis.set.assert_called_once()
    assert svc.neweventcount == 0


@pytest.mark.asyncio
@patch("app.services.event_identification_worker._last_event_list_update", 9999999999.0)
@patch("app.services.event_identification_worker.redis_client")
async def test_update_event_list_skips_within_debounce(mock_redis):
    """Called too soon after last update → debounce skips the write."""
    mock_redis.lock = MagicMock()

    svc = MagicMock()
    svc.neweventcount = 1

    from app.services.event_identification_worker import update_event_list_in_redis
    await update_event_list_in_redis(svc)

    mock_redis.lock.assert_not_called()


# ==========================================================
# flush_tickers()
# ==========================================================

@pytest.mark.asyncio
@patch("app.services.event_identification_worker.redis_client")
async def test_flush_tickers_empty(mock_redis):
    """No tickers accumulated → returns without calling pipeline."""
    import app.services.event_identification_worker as worker_mod
    worker_mod.all_tickers.clear()

    from app.services.event_identification_worker import flush_tickers
    await flush_tickers(MagicMock())

    mock_redis.pipeline.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.event_identification_worker.redis_client")
async def test_flush_tickers_writes_and_clears(mock_redis):
    """Tickers accumulated → pipeline sets each, clears all_tickers."""
    import app.services.event_identification_worker as worker_mod
    worker_mod.all_tickers.update({"AAPL", "MSFT"})

    pipe_mock = MagicMock()
    pipe_mock.execute = AsyncMock(return_value=[])
    mock_redis.pipeline = MagicMock(return_value=pipe_mock)

    from app.services.event_identification_worker import flush_tickers
    await flush_tickers(MagicMock())

    assert pipe_mock.set.call_count == 2
    assert len(worker_mod.all_tickers) == 0


# ==========================================================
# recover_pending_messages()
# ==========================================================

@pytest.mark.asyncio
@patch("app.services.event_identification_worker.process_message", new_callable=AsyncMock)
@patch("app.services.event_identification_worker.ticker_stream")
async def test_recover_pending_messages_calls_process(mock_ticker_stream, mock_process):
    """Pending messages → process_message called for each."""
    mock_ticker_stream.claim_pending = AsyncMock(
        return_value=[
            ("msg1", {"data": json.dumps({"id": "p1"})}),
            ("msg2", {"data": json.dumps({"id": "p2"})}),
        ]
    )

    from app.services.event_identification_worker import recover_pending_messages
    await recover_pending_messages(event_service=MagicMock())

    assert mock_process.call_count == 2


@pytest.mark.asyncio
@patch("app.services.event_identification_worker.ticker_stream")
async def test_recover_pending_messages_no_messages(mock_ticker_stream):
    """No pending messages → exits safely."""
    mock_ticker_stream.claim_pending = AsyncMock(return_value=[])

    from app.services.event_identification_worker import recover_pending_messages
    await recover_pending_messages(event_service=MagicMock())


@pytest.mark.asyncio
@patch("app.services.event_identification_worker.process_message", new_callable=AsyncMock)
@patch("app.services.event_identification_worker.ticker_stream")
async def test_recover_pending_logs_exceptions(mock_ticker_stream, mock_process):
    """process_message raises → exception captured, not re-raised."""
    mock_ticker_stream.claim_pending = AsyncMock(
        return_value=[("msg1", {"data": json.dumps({"id": "p1"})})]
    )
    mock_process.side_effect = Exception("failed")

    from app.services.event_identification_worker import recover_pending_messages
    await recover_pending_messages(event_service=MagicMock())  # should not raise


# ==========================================================
# cleanup_dead_consumers()
# ==========================================================

@pytest.mark.asyncio
@patch("app.services.event_identification_worker.redis_client")
async def test_cleanup_dead_consumers_removes_idle(mock_redis):
    """Consumer idle > 10 min with 0 pending → deleted."""
    mock_redis.xinfo_consumers = AsyncMock(
        return_value=[{"name": "dead_consumer", "idle": 700000, "pending": 0}]
    )
    mock_redis.xgroup_delconsumer = AsyncMock()

    from app.services.event_identification_worker import cleanup_dead_consumers
    await cleanup_dead_consumers()

    mock_redis.xgroup_delconsumer.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.event_identification_worker.redis_client")
async def test_cleanup_dead_consumers_keeps_consumer_with_pending(mock_redis):
    """Consumer with pending messages → not deleted."""
    mock_redis.xinfo_consumers = AsyncMock(
        return_value=[{"name": "busy_consumer", "idle": 700000, "pending": 3}]
    )
    mock_redis.xgroup_delconsumer = AsyncMock()

    from app.services.event_identification_worker import cleanup_dead_consumers
    await cleanup_dead_consumers()

    mock_redis.xgroup_delconsumer.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.event_identification_worker.CONSUMER_NAME", "eventidentification_abc123")
@patch("app.services.event_identification_worker.redis_client")
async def test_cleanup_dead_consumers_never_deletes_self(mock_redis):
    """Worker never deletes its own consumer entry."""
    mock_redis.xinfo_consumers = AsyncMock(
        return_value=[{"name": "eventidentification_abc123", "idle": 700000, "pending": 0}]
    )
    mock_redis.xgroup_delconsumer = AsyncMock()

    from app.services.event_identification_worker import cleanup_dead_consumers
    await cleanup_dead_consumers()

    mock_redis.xgroup_delconsumer.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.event_identification_worker.redis_client")
async def test_cleanup_dead_consumers_exception_swallowed(mock_redis):
    """xinfo_consumers raises → exception swallowed, no re-raise."""
    mock_redis.xinfo_consumers = AsyncMock(side_effect=Exception("Redis down"))

    from app.services.event_identification_worker import cleanup_dead_consumers
    await cleanup_dead_consumers()  # should not raise


# ==========================================================
# persist_event_list_to_bucket()
# ==========================================================

@pytest.mark.asyncio
@patch("app.services.event_identification_worker.redis_client")
async def test_persist_event_list_cancelled(mock_redis):
    """CancelledError from asyncio.sleep → re-raised."""
    mock_redis.set = AsyncMock()

    with patch("asyncio.sleep", side_effect=asyncio.CancelledError):
        from app.services.event_identification_worker import persist_event_list_to_bucket
        with pytest.raises(asyncio.CancelledError):
            await persist_event_list_to_bucket()
