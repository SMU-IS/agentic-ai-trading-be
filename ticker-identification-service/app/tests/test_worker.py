"""
Unit Tests — Ticker Identification Worker

We mock Redis + streams + ticker service completely.
No real Redis, S3, or LLM calls.
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ==========================================================
# decode_message()
# ==========================================================

from app.services.ticker_identification_worker import decode_message


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

def _make_ticker_service(result=None, new_alias_count=0, new_type_count=0):
    svc = MagicMock()
    svc.process_post = AsyncMock(return_value=result)
    svc.new_alias_count = new_alias_count
    svc.new_type_count = new_type_count
    return svc


@pytest.mark.asyncio
@patch("app.services.ticker_identification_worker.finalize_message", new_callable=AsyncMock)
@patch("app.services.ticker_identification_worker.ticker_stream")
@patch("app.services.ticker_identification_worker.redis_client")
async def test_process_message_success(mock_redis, mock_ticker_stream, mock_finalize):
    """Happy path: decodes → not duplicate → ticker found → saves → finalizes."""
    mock_redis.exists = AsyncMock(return_value=False)
    mock_redis.hset = AsyncMock()
    mock_redis.incr = AsyncMock()
    mock_ticker_stream.save = AsyncMock()

    svc = _make_ticker_service({"id": "p1", "ticker_metadata": {"AAPL": {"event_type": "earnings"}}})

    from app.services.ticker_identification_worker import process_message
    await process_message("msg1", {"data": json.dumps({"id": "p1"})}, ticker_service=svc)

    mock_ticker_stream.save.assert_called_once()
    mock_finalize.assert_called_once_with("msg1")


@pytest.mark.asyncio
@patch("app.services.ticker_identification_worker.finalize_message", new_callable=AsyncMock)
@patch("app.services.ticker_identification_worker.redis_client")
async def test_process_message_invalid_json(mock_redis, mock_finalize):
    """Invalid JSON → increments removed counter, finalizes immediately."""
    mock_redis.incr = AsyncMock()

    from app.services.ticker_identification_worker import process_message
    await process_message("msg1", {"data": "{bad json"}, ticker_service=MagicMock())

    mock_redis.incr.assert_called_once()
    mock_finalize.assert_called_once_with("msg1")


@pytest.mark.asyncio
@patch("app.services.ticker_identification_worker.finalize_message", new_callable=AsyncMock)
@patch("app.services.ticker_identification_worker.redis_client")
async def test_process_message_duplicate_skipped(mock_redis, mock_finalize):
    """Duplicate post → increments dup counter, finalizes without processing."""
    mock_redis.exists = AsyncMock(return_value=True)
    mock_redis.incr = AsyncMock()

    from app.services.ticker_identification_worker import process_message
    await process_message("msg1", {"data": json.dumps({"id": "p1"})}, ticker_service=MagicMock())

    mock_redis.incr.assert_called_once()
    mock_finalize.assert_called_once_with("msg1")


@pytest.mark.asyncio
@patch("app.services.ticker_identification_worker.finalize_message", new_callable=AsyncMock)
@patch("app.services.ticker_identification_worker.redis_client")
async def test_process_message_ticker_service_returns_none(mock_redis, mock_finalize):
    """ticker_service.process_post returns None → increments removed counter, finalizes."""
    mock_redis.exists = AsyncMock(return_value=False)
    mock_redis.hset = AsyncMock()
    mock_redis.incr = AsyncMock()

    from app.services.ticker_identification_worker import process_message
    await process_message("msg1", {"data": json.dumps({"id": "p1"})}, ticker_service=_make_ticker_service(None))

    mock_redis.incr.assert_called_once()
    mock_finalize.assert_called_once_with("msg1")


@pytest.mark.asyncio
@patch("app.services.ticker_identification_worker.finalize_message", new_callable=AsyncMock)
@patch("app.services.ticker_identification_worker.redis_client")
async def test_process_message_no_ticker_metadata_removed(mock_redis, mock_finalize):
    """ticker_metadata is empty → post removed, finalized without saving."""
    mock_redis.exists = AsyncMock(return_value=False)
    mock_redis.hset = AsyncMock()
    mock_redis.incr = AsyncMock()

    svc = _make_ticker_service({"id": "p1", "ticker_metadata": {}})

    from app.services.ticker_identification_worker import process_message
    await process_message("msg1", {"data": json.dumps({"id": "p1"})}, ticker_service=svc)

    mock_redis.incr.assert_called_once()
    mock_finalize.assert_called_once_with("msg1")


@pytest.mark.asyncio
@patch("app.services.ticker_identification_worker.finalize_message", new_callable=AsyncMock)
@patch("app.services.ticker_identification_worker.ticker_stream")
@patch("app.services.ticker_identification_worker.redis_client")
async def test_process_message_timestamps_written(mock_redis, mock_ticker_stream, _mock_finalize):
    """Both start and end timestamps written to Redis for a successful post."""
    mock_redis.exists = AsyncMock(return_value=False)
    mock_redis.hset = AsyncMock()
    mock_redis.incr = AsyncMock()
    mock_ticker_stream.save = AsyncMock()

    svc = _make_ticker_service({"id": "p1", "ticker_metadata": {"AAPL": {}}})

    from app.services.ticker_identification_worker import process_message
    await process_message("msg1", {"data": json.dumps({"id": "p1"})}, ticker_service=svc)

    assert mock_redis.hset.call_count == 2
    fields = [call.args[1] for call in mock_redis.hset.call_args_list]
    assert "ticker_timestamp_start" in fields
    assert "ticker_timestamp" in fields


@pytest.mark.asyncio
@patch("app.services.ticker_identification_worker.finalize_message", new_callable=AsyncMock)
@patch("app.services.ticker_identification_worker.ticker_stream")
@patch("app.services.ticker_identification_worker.redis_client")
async def test_process_message_cancelled_error_reraises(mock_redis, mock_ticker_stream, _mock_finalize):
    """CancelledError from ticker_stream.save → re-raised (not swallowed)."""
    mock_redis.exists = AsyncMock(return_value=False)
    mock_redis.hset = AsyncMock()
    mock_redis.incr = AsyncMock()
    mock_ticker_stream.save = AsyncMock(side_effect=asyncio.CancelledError)

    svc = _make_ticker_service({"id": "p1", "ticker_metadata": {"AAPL": {}}})

    from app.services.ticker_identification_worker import process_message
    with pytest.raises(asyncio.CancelledError):
        await process_message("msg1", {"data": json.dumps({"id": "p1"})}, ticker_service=svc)


# ==========================================================
# setup_consumer_group()
# ==========================================================

@pytest.mark.asyncio
@patch("app.services.ticker_identification_worker.preproc_stream")
async def test_setup_consumer_group_success(mock_preproc_stream):
    """Consumer group created successfully → create_consumer_group called once."""
    mock_preproc_stream.create_consumer_group = AsyncMock()

    from app.services.ticker_identification_worker import setup_consumer_group
    await setup_consumer_group()

    mock_preproc_stream.create_consumer_group.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.ticker_identification_worker.preproc_stream")
async def test_setup_consumer_group_already_exists_swallowed(mock_preproc_stream):
    """Exception from create_consumer_group → swallowed, no raise."""
    mock_preproc_stream.create_consumer_group = AsyncMock(side_effect=Exception("BUSYGROUP"))

    from app.services.ticker_identification_worker import setup_consumer_group
    await setup_consumer_group()  # should not raise


# ==========================================================
# finalize_message()
# ==========================================================

@pytest.mark.asyncio
@patch("app.services.ticker_identification_worker.redis_client")
async def test_finalize_message_pipeline(mock_redis):
    """finalize_message uses pipeline to XACK and XDEL atomically."""
    pipe_mock = AsyncMock()
    pipe_mock.__aenter__ = AsyncMock(return_value=pipe_mock)
    pipe_mock.__aexit__ = AsyncMock(return_value=False)
    mock_redis.pipeline = MagicMock(return_value=pipe_mock)

    from app.services.ticker_identification_worker import finalize_message
    await finalize_message("msg_id_1")

    pipe_mock.xack.assert_called_once()
    pipe_mock.xdel.assert_called_once()
    pipe_mock.execute.assert_called_once()


# ==========================================================
# send_heartbeat()
# ==========================================================

@pytest.mark.asyncio
@patch("app.services.ticker_identification_worker.redis_client")
async def test_send_heartbeat_cancelled(mock_redis):
    """CancelledError from asyncio.sleep → re-raised after logging."""
    mock_redis.set = AsyncMock()

    with patch("asyncio.sleep", side_effect=asyncio.CancelledError):
        from app.services.ticker_identification_worker import send_heartbeat
        with pytest.raises(asyncio.CancelledError):
            await send_heartbeat()

    mock_redis.set.assert_called_once()


# ==========================================================
# recover_pending_messages()
# ==========================================================

@pytest.mark.asyncio
@patch("app.services.ticker_identification_worker.preproc_stream")
@patch("app.services.ticker_identification_worker.process_message", new_callable=AsyncMock)
async def test_recover_pending_messages_calls_process(mock_process, mock_preproc_stream):
    """Pending messages → process_message called for each."""
    mock_preproc_stream.claim_pending = AsyncMock(
        return_value=[
            ("msg1", {"data": json.dumps({"id": "p1"})}),
            ("msg2", {"data": json.dumps({"id": "p2"})}),
        ]
    )

    from app.services.ticker_identification_worker import recover_pending_messages
    await recover_pending_messages(ticker_service=MagicMock())

    assert mock_process.call_count == 2


@pytest.mark.asyncio
@patch("app.services.ticker_identification_worker.preproc_stream")
async def test_recover_pending_messages_no_messages(mock_preproc_stream):
    """No pending messages → exits safely."""
    mock_preproc_stream.claim_pending = AsyncMock(return_value=[])

    from app.services.ticker_identification_worker import recover_pending_messages
    await recover_pending_messages(ticker_service=MagicMock())


@pytest.mark.asyncio
@patch("app.services.ticker_identification_worker.preproc_stream")
@patch("app.services.ticker_identification_worker.process_message", new_callable=AsyncMock)
async def test_recover_pending_logs_exceptions(mock_process, mock_preproc_stream):
    """process_message raises → exception captured by gather, logged, not re-raised."""
    mock_preproc_stream.claim_pending = AsyncMock(
        return_value=[("msg1", {"data": json.dumps({"id": "p1"})})]
    )
    mock_process.side_effect = Exception("processing blew up")

    from app.services.ticker_identification_worker import recover_pending_messages
    await recover_pending_messages(ticker_service=MagicMock())  # should not raise


# ==========================================================
# cleanup_dead_consumers()
# ==========================================================

@pytest.mark.asyncio
@patch("app.services.ticker_identification_worker.redis_client")
async def test_cleanup_dead_consumers_removes_idle(mock_redis):
    """Consumer idle > 10 min with 0 pending → deleted."""
    mock_redis.xinfo_consumers = AsyncMock(
        return_value=[{"name": "dead_consumer", "idle": 20 * 60 * 1000, "pending": 0}]
    )
    mock_redis.xgroup_delconsumer = AsyncMock()

    from app.services.ticker_identification_worker import cleanup_dead_consumers
    await cleanup_dead_consumers()

    mock_redis.xgroup_delconsumer.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.ticker_identification_worker.redis_client")
async def test_cleanup_dead_consumers_keeps_consumer_with_pending(mock_redis):
    """Idle consumer with pending messages → not deleted."""
    mock_redis.xinfo_consumers = AsyncMock(
        return_value=[{"name": "busy_consumer", "idle": 700000, "pending": 3}]
    )
    mock_redis.xgroup_delconsumer = AsyncMock()

    from app.services.ticker_identification_worker import cleanup_dead_consumers
    await cleanup_dead_consumers()

    mock_redis.xgroup_delconsumer.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.ticker_identification_worker.CONSUMER_NAME", "tickeridentification_abc123")
@patch("app.services.ticker_identification_worker.redis_client")
async def test_cleanup_dead_consumers_never_deletes_self(mock_redis):
    """Worker never deletes its own consumer entry, even if idle."""
    mock_redis.xinfo_consumers = AsyncMock(
        return_value=[{"name": "tickeridentification_abc123", "idle": 700000, "pending": 0}]
    )
    mock_redis.xgroup_delconsumer = AsyncMock()

    from app.services.ticker_identification_worker import cleanup_dead_consumers
    await cleanup_dead_consumers()

    mock_redis.xgroup_delconsumer.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.ticker_identification_worker.redis_client")
async def test_cleanup_dead_consumers_exception_swallowed(mock_redis):
    """xinfo_consumers raises → exception swallowed, no re-raise."""
    mock_redis.xinfo_consumers = AsyncMock(side_effect=Exception("Redis down"))

    from app.services.ticker_identification_worker import cleanup_dead_consumers
    await cleanup_dead_consumers()  # should not raise


# ==========================================================
# load_static_state()
# ==========================================================

@pytest.mark.asyncio
@patch("app.services.ticker_identification_worker.redis_client")
async def test_load_static_state_from_redis(mock_redis):
    """Data found in Redis → returned directly, bucket never called."""
    mock_redis.get = AsyncMock(return_value='{"AAPL": "Apple"}')

    from app.services.ticker_identification_worker import load_static_state
    result = await load_static_state("some_redis_key", "some/bucket/key.json")

    assert result == {"AAPL": "Apple"}
    mock_redis.set.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.ticker_identification_worker.bucket")
@patch("app.services.ticker_identification_worker.redis_client")
async def test_load_static_state_falls_back_to_bucket(mock_redis, mock_bucket):
    """Redis empty → loads from bucket, caches in Redis, returns parsed data."""
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock()
    mock_bucket.read_text.return_value = '{"MSFT": "Microsoft"}'

    from app.services.ticker_identification_worker import load_static_state
    result = await load_static_state("some_redis_key", "some/bucket/key.json")

    assert result == {"MSFT": "Microsoft"}
    mock_redis.set.assert_called_once_with("some_redis_key", '{"MSFT": "Microsoft"}')


# ==========================================================
# init_ticker_service()
# ==========================================================

@pytest.mark.asyncio
@patch("app.services.ticker_identification_worker.TickerIdentificationService")
@patch("app.services.ticker_identification_worker.load_static_state", new_callable=AsyncMock)
async def test_init_ticker_service(mock_load, mock_ticker_cls):
    """init_ticker_service loads both static states and constructs the service."""
    mock_load.side_effect = [{"AAPL": {}}, {"apple": "AAPL"}]

    from app.services.ticker_identification_worker import init_ticker_service
    await init_ticker_service()

    assert mock_load.call_count == 2
    mock_ticker_cls.assert_called_once_with(
        cleaned_tickers={"AAPL": {}},
        alias_to_canonical={"apple": "AAPL"},
    )


# ==========================================================
# persist_if_changed()
# ==========================================================

@pytest.mark.asyncio
@patch("app.services.ticker_identification_worker.redis_client")
async def test_persist_if_changed_skips_when_no_changes(mock_redis):
    """No new aliases or types → returns immediately without acquiring lock."""
    mock_redis.lock = MagicMock()

    svc = MagicMock()
    svc.new_alias_count = 0
    svc.new_type_count = 0

    from app.services.ticker_identification_worker import persist_if_changed
    await persist_if_changed(svc)

    mock_redis.lock.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.ticker_identification_worker._last_persist_time", 0.0)
@patch("app.services.ticker_identification_worker.redis_client")
async def test_persist_if_changed_updates_alias(mock_redis):
    """New aliases present → acquires lock, writes alias mapping to Redis."""
    lock_mock = AsyncMock()
    lock_mock.__aenter__ = AsyncMock(return_value=lock_mock)
    lock_mock.__aexit__ = AsyncMock(return_value=False)
    mock_redis.lock = MagicMock(return_value=lock_mock)
    mock_redis.set = AsyncMock()

    svc = MagicMock()
    svc.new_alias_count = 2
    svc.new_type_count = 0
    svc.alias_to_canonical = {"apple": "AAPL"}

    from app.services.ticker_identification_worker import persist_if_changed
    await persist_if_changed(svc)

    mock_redis.set.assert_called_once()
    assert svc.new_alias_count == 0


@pytest.mark.asyncio
@patch("app.services.ticker_identification_worker._last_persist_time", 0.0)
@patch("app.services.ticker_identification_worker.redis_client")
async def test_persist_if_changed_updates_cleaned_tickers(mock_redis):
    """New ticker types present → acquires lock, writes cleaned tickers to Redis."""
    lock_mock = AsyncMock()
    lock_mock.__aenter__ = AsyncMock(return_value=lock_mock)
    lock_mock.__aexit__ = AsyncMock(return_value=False)
    mock_redis.lock = MagicMock(return_value=lock_mock)
    mock_redis.set = AsyncMock()

    svc = MagicMock()
    svc.new_alias_count = 0
    svc.new_type_count = 1
    svc.cleaned_tickers = {"AAPL": {"type": "equity"}}

    from app.services.ticker_identification_worker import persist_if_changed
    await persist_if_changed(svc)

    mock_redis.set.assert_called_once()
    assert svc.new_type_count == 0


# ==========================================================
# persist_static_state()
# ==========================================================

@pytest.mark.asyncio
@patch("app.services.ticker_identification_worker._last_persist_time", 9999999999.0)
@patch("app.services.ticker_identification_worker.redis_client")
async def test_persist_if_changed_skips_within_debounce(mock_redis):
    """Called too soon after last persist → debounce skips the write."""
    mock_redis.lock = MagicMock()

    svc = MagicMock()
    svc.new_alias_count = 1
    svc.new_type_count = 0

    from app.services.ticker_identification_worker import persist_if_changed
    await persist_if_changed(svc)

    mock_redis.lock.assert_not_called()


# ==========================================================
# persist_static_state() — write-to-bucket path
# ==========================================================


@pytest.mark.asyncio
@patch("app.services.ticker_identification_worker.bucket")
@patch("app.services.ticker_identification_worker.redis_client")
async def test_persist_static_state_cancelled(mock_redis, _mock_bucket):
    """CancelledError from asyncio.sleep → re-raised."""
    mock_redis.get = AsyncMock(return_value=None)

    with patch("asyncio.sleep", side_effect=asyncio.CancelledError):
        from app.services.ticker_identification_worker import persist_static_state
        with pytest.raises(asyncio.CancelledError):
            await persist_static_state()
