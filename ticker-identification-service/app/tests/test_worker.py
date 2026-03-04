"""
Unit Tests — Ticker Identification Worker

We mock Redis + streams completely.
No real Redis or bucket calls.
"""

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

@pytest.mark.asyncio
@patch("app.services.ticker_identification_worker.redis_client")
@patch("app.services.ticker_identification_worker.ticker_stream")
@patch("app.services.ticker_identification_worker.finalize_message", new_callable=AsyncMock)
async def test_process_message_success(
    mock_finalize,
    mock_ticker_stream,
    mock_redis_client,
):
    """
    Happy path:
    - process_post returns ticker data
    - save called
    - finalize called
    """

    # -------------------------
    # Mock ticker service
    # -------------------------
    mock_ticker_service = MagicMock()
    mock_ticker_service.process_post.return_value = {
        "id": "p1",
        "ticker_metadata": {
            "AAPL": {"event_type": "earnings"}
        }
    }

    mock_ticker_service.neweventcount = 1

    # 🔥 ADD THIS
    mock_ticker_service.new_alias_count = 0
    mock_ticker_service.new_type_count = 0

    # -------------------------
    # Mock redis operations
    # -------------------------
    mock_redis_client.incr = AsyncMock()
    mock_redis_client.delete = AsyncMock()

    # -------------------------
    # Mock stream save
    # -------------------------
    mock_ticker_stream.save = AsyncMock()

    from app.services.ticker_identification_worker import process_message

    await process_message(
        "msg1",
        {"data": json.dumps({"id": "p1"})},
        ticker_service=mock_ticker_service,
    )

    mock_ticker_stream.save.assert_called_once()
    mock_finalize.assert_called_once_with("msg1")


# ==========================================================
# Invalid JSON
# ==========================================================

@pytest.mark.asyncio
@patch(
    "app.services.ticker_identification_worker.finalize_message",
    new_callable=AsyncMock,
)
async def test_process_message_invalid_json(mock_finalize):
    from app.services.ticker_identification_worker import process_message

    await process_message(
        "msg1",
        {"data": "{bad json"},
        ticker_service=MagicMock(),
    )

    mock_finalize.assert_called_once_with("msg1")


# ==========================================================
# analyse_event returns None
# ==========================================================

@pytest.mark.asyncio
@patch(
    "app.services.ticker_identification_worker.finalize_message",
    new_callable=AsyncMock,
)
async def test_process_message_event_service_returns_none(mock_finalize):
    mock_ticker_service = MagicMock()
    mock_ticker_service.process_post.return_value = None
    mock_ticker_service.neweventcount = 0

    from app.services.ticker_identification_worker import process_message

    await process_message(
        "msg1",
        {"data": json.dumps({"id": "p1"})},
        ticker_service=mock_ticker_service,
    )

    mock_finalize.assert_called_once_with("msg1")


# ==========================================================
# recover_pending_messages()
# ==========================================================

@pytest.mark.asyncio
@patch("app.services.ticker_identification_worker.preproc_stream")
@patch("app.services.ticker_identification_worker.process_message", new_callable=AsyncMock)
async def test_recover_pending_messages_calls_process(
    mock_process,
    mock_preproc_stream,
):
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
    mock_preproc_stream.claim_pending = AsyncMock(return_value=[])

    from app.services.ticker_identification_worker import recover_pending_messages

    await recover_pending_messages(ticker_service=MagicMock())


# ==========================================================
# cleanup_dead_consumers()
# ==========================================================

@pytest.mark.asyncio
@patch("app.services.ticker_identification_worker.redis_client")
async def test_cleanup_dead_consumers_removes_idle(mock_redis):
    mock_redis.xinfo_consumers = AsyncMock(
        return_value=[
            {
                "name": "dead_consumer",
                "idle": 20 * 60 * 1000,
                "pending": 0,
            }
        ]
    )

    mock_redis.xgroup_delconsumer = AsyncMock()

    from app.services.ticker_identification_worker import cleanup_dead_consumers

    await cleanup_dead_consumers()

    mock_redis.xgroup_delconsumer.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.ticker_identification_worker.redis_client")
async def test_cleanup_dead_consumers_keeps_active_consumer(mock_redis):
    mock_redis.xinfo_consumers = AsyncMock(
        return_value=[
            {
                "name": "tickeridentification_worker_test",
                "idle": 100,
                "pending": 0,
            }
        ]
    )

    mock_redis.xgroup_delconsumer = AsyncMock()

    from app.services.ticker_identification_worker import cleanup_dead_consumers

    await cleanup_dead_consumers()

    mock_redis.xgroup_delconsumer.assert_not_called()