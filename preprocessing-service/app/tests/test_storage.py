"""
Unit Tests — RedisStreamStorage
File: app/tests/test_storage.py

Run from preprocessing-service/:
    pytest
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from redis.exceptions import ResponseError

from app.scripts.storage import RedisStreamStorage


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_redis():
    return AsyncMock()


@pytest.fixture
def storage(mock_redis):
    return RedisStreamStorage("test_stream", mock_redis)


# ─── save() — happy path ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_save_new_message_success(storage, mock_redis):
    """New post_id → dedup lock acquired, message saved to stream."""
    mock_redis.set.return_value = True
    mock_redis.xadd.return_value = "1234567890-0"

    msg_id = await storage.save({"id": "post_001", "content": "some text"})

    assert msg_id == "1234567890-0"
    mock_redis.set.assert_called_once_with(
        "preproc_dedup:post_001", "1", nx=True, ex=60 * 60 * 24 * 4
    )
    mock_redis.xadd.assert_called_once()


@pytest.mark.asyncio
async def test_save_serializes_all_fields_as_json(storage, mock_redis):
    """All fields in the item are JSON-serialized before being written to the stream."""
    mock_redis.set.return_value = True
    mock_redis.xadd.return_value = "msg_id"

    await storage.save({"id": "post_002", "score": 0.85, "tags": ["AAPL", "MSFT"]})

    stream_data = mock_redis.xadd.call_args[0][1]
    assert stream_data["id"] == json.dumps("post_002")
    assert stream_data["score"] == json.dumps(0.85)
    assert stream_data["tags"] == json.dumps(["AAPL", "MSFT"])


# ─── save() — sad path ────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_save_duplicate_skipped(storage, mock_redis):
    """Duplicate post_id (dedup key exists) → None returned, xadd never called."""
    mock_redis.set.return_value = False

    msg_id = await storage.save({"id": "post_001", "content": "duplicate"})

    assert msg_id is None
    mock_redis.xadd.assert_not_called()


@pytest.mark.asyncio
async def test_save_missing_id_proceeds_with_none_key(storage, mock_redis):
    """Item without 'id' key → dict.get() returns None (no KeyError raised),
    so save proceeds using 'preproc_dedup:None' as the dedup key."""
    mock_redis.set.return_value = True
    mock_redis.xadd.return_value = "1234567890-0"

    msg_id = await storage.save({"content": "no id field here"})

    # Code does NOT return None — it continues with post_id=None
    assert msg_id == "1234567890-0"
    mock_redis.set.assert_called_once_with(
        "preproc_dedup:None", "1", nx=True, ex=60 * 60 * 24 * 4
    )


# ─── save_batch() ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_save_batch_writes_all_items(storage, mock_redis):
    """Batch of N items → pipeline.xadd called N times."""
    # pipeline() is called synchronously (no await), so use a plain MagicMock.
    # Only pipeline.execute() is awaited, so it needs to be an AsyncMock.
    pipeline_mock = MagicMock()
    pipeline_mock.execute = AsyncMock(return_value=["id1", "id2", "id3"])
    mock_redis.pipeline = MagicMock(return_value=pipeline_mock)

    items = [
        {"id": "p1", "data": "a"},
        {"id": "p2", "data": "b"},
        {"id": "p3", "data": "c"},
    ]

    results = await storage.save_batch(items)

    assert results == ["id1", "id2", "id3"]
    assert pipeline_mock.xadd.call_count == 3


@pytest.mark.asyncio
async def test_save_batch_empty_list(storage, mock_redis):
    """Empty item list → pipeline runs with no xadd calls."""
    pipeline_mock = MagicMock()
    pipeline_mock.execute = AsyncMock(return_value=[])
    mock_redis.pipeline = MagicMock(return_value=pipeline_mock)

    results = await storage.save_batch([])

    assert results == []
    pipeline_mock.xadd.assert_not_called()


# ─── create_consumer_group() ──────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_create_consumer_group_success(storage, mock_redis):
    """New group created → returns True, xgroup_create called with correct args."""
    mock_redis.xgroup_create.return_value = True

    result = await storage.create_consumer_group("my_group")

    assert result is True
    mock_redis.xgroup_create.assert_called_once_with(
        name="test_stream",
        groupname="my_group",
        id="0",
        mkstream=True,
    )


@pytest.mark.asyncio
async def test_create_consumer_group_already_exists(storage, mock_redis):
    """BUSYGROUP error → returns False without raising."""
    mock_redis.xgroup_create.side_effect = ResponseError(
        "BUSYGROUP Consumer Group name already exists"
    )

    result = await storage.create_consumer_group("existing_group")

    assert result is False


@pytest.mark.asyncio
async def test_create_consumer_group_other_error_raises(storage, mock_redis):
    """Non-BUSYGROUP Redis error → propagated to caller."""
    mock_redis.xgroup_create.side_effect = ResponseError("Some other error")

    with pytest.raises(ResponseError):
        await storage.create_consumer_group("my_group")


# ─── read_group() ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_read_group_success(storage, mock_redis):
    """Messages returned from xreadgroup → deserialized and returned as list of tuples."""
    mock_redis.xreadgroup.return_value = [
        (
            "test_stream",
            [("msg_id_1", {"id": '"post_001"', "score": "0.85", "label": '"positive"'})],
        )
    ]

    results = await storage.read_group("my_group", "consumer_1")

    assert len(results) == 1
    msg_id, data = results[0]
    assert msg_id == "msg_id_1"
    assert data["id"] == "post_001"
    assert data["score"] == 0.85
    assert data["label"] == "positive"


@pytest.mark.asyncio
async def test_read_group_nogroup_recreates_and_retries(storage, mock_redis):
    """NOGROUP error → group recreated, xreadgroup retried successfully."""
    mock_redis.xgroup_create.return_value = True
    mock_redis.xreadgroup.side_effect = [
        ResponseError("NOGROUP No such consumer group"),
        [("test_stream", [("msg_id_2", {"id": '"post_002"'})])],
    ]

    results = await storage.read_group("missing_group", "consumer_1")

    assert mock_redis.xgroup_create.call_count == 1
    assert mock_redis.xreadgroup.call_count == 2
    assert len(results) == 1


@pytest.mark.asyncio
async def test_read_group_empty_stream(storage, mock_redis):
    """No messages available → returns empty list."""
    mock_redis.xreadgroup.return_value = []

    results = await storage.read_group("my_group", "consumer_1")

    assert results == []


@pytest.mark.asyncio
async def test_read_group_uses_pending_id_when_requested(storage, mock_redis):
    """pending=True → read_id is '0' (redelivery), not '>' (new messages)."""
    mock_redis.xreadgroup.return_value = []

    await storage.read_group("my_group", "consumer_1", pending=True)

    call_kwargs = mock_redis.xreadgroup.call_args
    stream_arg = call_kwargs[0][2]  # positional: group, consumer, streams_dict
    assert stream_arg == {"test_stream": "0"}


# ─── acknowledge() ────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_acknowledge_single_message(storage, mock_redis):
    """xack called with correct stream name, group, and message ID."""
    mock_redis.xack.return_value = 1

    result = await storage.acknowledge("my_group", "msg_id_1")

    assert result == 1
    mock_redis.xack.assert_called_once_with("test_stream", "my_group", "msg_id_1")


@pytest.mark.asyncio
async def test_acknowledge_no_ids_returns_zero(storage, mock_redis):
    """No message IDs passed → returns 0 without calling xack."""
    result = await storage.acknowledge("my_group")

    assert result == 0
    mock_redis.xack.assert_not_called()


# ─── delete() ─────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_delete_messages_success(storage, mock_redis):
    """xdel called with correct args → returns count of deleted messages."""
    mock_redis.xdel.return_value = 2

    result = await storage.delete("msg_id_1", "msg_id_2")

    assert result == 2
    mock_redis.xdel.assert_called_once_with("test_stream", "msg_id_1", "msg_id_2")


@pytest.mark.asyncio
async def test_delete_no_ids_returns_zero(storage, mock_redis):
    """No IDs passed → returns 0, xdel never called."""
    result = await storage.delete()

    assert result == 0
    mock_redis.xdel.assert_not_called()


@pytest.mark.asyncio
async def test_delete_xdel_raises_returns_zero(storage, mock_redis):
    """xdel raises an exception → returns 0 without propagating."""
    mock_redis.xdel.side_effect = Exception("connection lost")

    result = await storage.delete("msg_id_1")

    assert result == 0


# ─── claim_pending() ──────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_claim_pending_no_pending_messages(storage, mock_redis):
    """No pending messages → returns empty list, xclaim never called."""
    mock_redis.xpending_range.return_value = []

    result = await storage.claim_pending("my_group", "consumer_1")

    assert result == []
    mock_redis.xclaim.assert_not_called()


@pytest.mark.asyncio
async def test_claim_pending_skips_messages_not_idle_long_enough(storage, mock_redis):
    """Pending messages below min_idle_time_ms threshold → not claimed."""
    mock_redis.xpending_range.return_value = [
        {"message_id": "msg_id_1", "time_since_delivered": 100},  # < 5000ms
    ]

    result = await storage.claim_pending("my_group", "consumer_1", min_idle_time_ms=5000)

    assert result == []
    mock_redis.xclaim.assert_not_called()


@pytest.mark.asyncio
async def test_claim_pending_claims_idle_messages(storage, mock_redis):
    """Idle message above threshold → xclaim called and results returned."""
    mock_redis.xpending_range.return_value = [
        {"message_id": "msg_id_1", "time_since_delivered": 10000},  # > 5000ms
    ]
    mock_redis.xclaim.return_value = [
        ("msg_id_1", {"id": '"post_001"'}),
    ]

    result = await storage.claim_pending("my_group", "consumer_1", min_idle_time_ms=5000)

    mock_redis.xclaim.assert_called_once()
    assert len(result) == 1
    msg_id, data = result[0]
    assert msg_id == "msg_id_1"
    assert data["id"] == "post_001"


# ─── _deserialize_dict() ──────────────────────────────────────────────────────

def test_deserialize_dict_valid_json_values(storage):
    """JSON-encoded values → deserialized to Python objects."""
    raw = {
        "id": '"post_001"',
        "score": "0.85",
        "tags": '["AAPL", "MSFT"]',
        "meta": '{"source": "reddit"}',
    }

    result = storage._deserialize_dict(raw)

    assert result["id"] == "post_001"
    assert result["score"] == 0.85
    assert result["tags"] == ["AAPL", "MSFT"]
    assert result["meta"] == {"source": "reddit"}


def test_deserialize_dict_invalid_json_passes_through(storage):
    """Non-JSON string → returned as raw string without raising."""
    raw = {"key": "not{{valid::json"}

    result = storage._deserialize_dict(raw)

    assert result["key"] == "not{{valid::json"


def test_deserialize_dict_mixed_values(storage):
    """Mix of valid JSON and raw strings → each handled correctly."""
    raw = {
        "id": '"post_123"',           # valid JSON string
        "raw_value": "plain-text",    # not valid JSON
        "count": "42",                # valid JSON number
    }

    result = storage._deserialize_dict(raw)

    assert result["id"] == "post_123"
    assert result["raw_value"] == "plain-text"
    assert result["count"] == 42
