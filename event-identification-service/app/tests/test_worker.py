"""
Unit Tests — Event Identification Worker
"""

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

@pytest.mark.asyncio
@patch("app.services.event_identification_worker.redis_client")
@patch(
    "app.services.event_identification_worker.finalize_message",
    new_callable=AsyncMock,
)
@patch("app.services.event_identification_worker.event_stream")
async def test_process_message_success(
    mock_event_stream,
    mock_finalize,
    mock_redis_client,
):
    """
    Happy path:
    - analyse returns event
    - save called
    - finalize called
    - redis lock mocked properly
    """

    # ===============================
    # 🔥 Mock Redis fully
    # ===============================
    mock_redis_client.get = AsyncMock(return_value=None)
    mock_redis_client.set = AsyncMock()

    # 🔥 Mock lock properly as async context manager
    mock_lock = MagicMock()
    mock_lock.__aenter__ = AsyncMock(return_value=None)
    mock_lock.__aexit__ = AsyncMock(return_value=None)

    mock_redis_client.lock = MagicMock(return_value=mock_lock)

    # ===============================
    # Mock event service
    # ===============================
    mock_event_service = MagicMock()
    mock_event_service.analyse_event.return_value = {
        "id": "p1",
        "ticker_metadata": {
            "AAPL": {"event_type": "earnings"}
        }
    }
    mock_event_service.neweventcount = 1

    # ===============================
    # Mock event_stream.save
    # ===============================
    mock_event_stream.save = AsyncMock()

    from app.services.event_identification_worker import process_message

    await process_message(
        "msg1",
        {"data": json.dumps({"id": "p1"})},
        event_service=mock_event_service,
    )

    # Assertions
    mock_event_stream.save.assert_called_once()
    mock_finalize.assert_called_once_with("msg1")


@pytest.mark.asyncio
@patch(
    "app.services.event_identification_worker.finalize_message",
    new_callable=AsyncMock,
)
async def test_process_message_invalid_json(mock_finalize):
    """
    Invalid JSON → should finalize immediately
    """

    from app.services.event_identification_worker import process_message

    await process_message(
        "msg1",
        {"data": "{bad json"},
        event_service=MagicMock(),
    )

    mock_finalize.assert_called_once_with("msg1")


@pytest.mark.asyncio
@patch(
    "app.services.event_identification_worker.finalize_message",
    new_callable=AsyncMock,
)
async def test_process_message_event_service_returns_none(mock_finalize):
    """
    If analyse_event returns None → finalize should be called
    """

    mock_event_service = MagicMock()
    mock_event_service.analyse_event.return_value = None
    mock_event_service.neweventcount = 0

    from app.services.event_identification_worker import process_message

    await process_message(
        "msg1",
        {"data": json.dumps({"id": "p1"})},
        event_service=mock_event_service,
    )

    mock_finalize.assert_called_once_with("msg1")


# ==========================================================
# recover_pending_messages()
# ==========================================================

@pytest.mark.asyncio
@patch(
    "app.services.event_identification_worker.process_message",
    new_callable=AsyncMock,
)
@patch("app.services.event_identification_worker.ticker_stream")
async def test_recover_pending_messages_calls_process(
    mock_ticker_stream,
    mock_process,
):
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
    mock_ticker_stream.claim_pending = AsyncMock(return_value=[])

    from app.services.event_identification_worker import recover_pending_messages

    await recover_pending_messages(event_service=MagicMock())


# ==========================================================
# cleanup_dead_consumers()
# ==========================================================

@pytest.mark.asyncio
@patch("app.services.event_identification_worker.redis_client")
async def test_cleanup_dead_consumers_removes_idle(mock_redis):
    mock_redis.xinfo_consumers = AsyncMock(
        return_value=[
            {
                "name": "dead_consumer",
                "idle": 700000,
                "pending": 0,
            }
        ]
    )

    from app.services.event_identification_worker import cleanup_dead_consumers

    await cleanup_dead_consumers()

    mock_redis.xgroup_delconsumer.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.event_identification_worker.redis_client")
async def test_cleanup_dead_consumers_keeps_active_consumer(mock_redis):
    mock_redis.xinfo_consumers = AsyncMock(
        return_value=[
            {
                "name": "event_identification_worker_test",
                "idle": 100,
                "pending": 0,
            }
        ]
    )

    from app.services.event_identification_worker import cleanup_dead_consumers

    await cleanup_dead_consumers()

    mock_redis.xgroup_delconsumer.assert_not_called()