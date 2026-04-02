"""
Unit Tests — RedisStreamStorage
File: app/tests/test_storage.py

Run from qdrant-retrieval/:
    pytest
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from redis.exceptions import ResponseError

from app.scripts.storage import RedisStreamStorage


def _make_storage(stream_name="test_stream"):
    mock_redis = MagicMock()
    return RedisStreamStorage(stream_name, mock_redis), mock_redis


# ─── save() ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_save_success():
    storage, r = _make_storage()
    r.set = AsyncMock(return_value=True)
    r.xadd = AsyncMock(return_value="1234-0")

    result = await storage.save({"id": "post_001", "content": "hello"})

    assert result == "1234-0"
    r.set.assert_called_once()
    r.xadd.assert_called_once()


@pytest.mark.asyncio
async def test_save_duplicate_returns_none():
    storage, r = _make_storage()
    r.set = AsyncMock(return_value=None)  # nx=True → not acquired

    result = await storage.save({"id": "post_001"})

    assert result is None
    r.xadd.assert_not_called() if hasattr(r, "xadd") else None


@pytest.mark.asyncio
async def test_save_sets_correct_dedup_key():
    storage, r = _make_storage()
    r.set = AsyncMock(return_value=True)
    r.xadd = AsyncMock(return_value="1234-0")

    await storage.save({"id": "reddit:abc123"})

    call_args = r.set.call_args
    assert call_args[0][0] == "qdrant_dedup:reddit:abc123"
    assert call_args[1]["nx"] is True
    assert call_args[1]["ex"] == 60 * 60 * 24 * 5


@pytest.mark.asyncio
async def test_save_serializes_values_to_json():
    storage, r = _make_storage()
    r.set = AsyncMock(return_value=True)
    r.xadd = AsyncMock(return_value="1234-0")

    await storage.save({"id": "p1", "content": {"title": "hello"}})

    call_args = r.xadd.call_args[0][1]
    assert json.loads(call_args["content"]) == {"title": "hello"}


# ─── create_consumer_group() ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_consumer_group_success():
    storage, r = _make_storage()
    r.xgroup_create = AsyncMock(return_value=True)

    result = await storage.create_consumer_group("my_group")

    assert result is True
    r.xgroup_create.assert_called_once()


@pytest.mark.asyncio
async def test_create_consumer_group_already_exists():
    storage, r = _make_storage()
    r.xgroup_create = AsyncMock(side_effect=ResponseError("BUSYGROUP already exists"))

    result = await storage.create_consumer_group("my_group")

    assert result is False


@pytest.mark.asyncio
async def test_create_consumer_group_other_error_raises():
    storage, r = _make_storage()
    r.xgroup_create = AsyncMock(side_effect=ResponseError("some other error"))

    with pytest.raises(ResponseError):
        await storage.create_consumer_group("my_group")


# ─── read_group() ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_read_group_returns_deserialized_messages():
    storage, r = _make_storage()
    raw = [("test_stream", [("msg_1", {"data": json.dumps({"id": "p1"})})])]
    r.xreadgroup = AsyncMock(return_value=raw)

    results = await storage.read_group("grp", "consumer1")

    assert len(results) == 1
    msg_id, data = results[0]
    assert msg_id == "msg_1"
    assert data["data"] == {"id": "p1"}


@pytest.mark.asyncio
async def test_read_group_recreates_group_on_nogroup():
    storage, r = _make_storage()
    raw = [("test_stream", [("msg_1", {"data": '{"id": "p1"}'})])]
    r.xreadgroup = AsyncMock(side_effect=[
        ResponseError("NOGROUP no such group"),
        raw,
    ])
    r.xgroup_create = AsyncMock(return_value=True)

    results = await storage.read_group("grp", "consumer1")

    assert len(results) == 1
    assert r.xgroup_create.call_count == 1


@pytest.mark.asyncio
async def test_read_group_raises_non_nogroup_error():
    storage, r = _make_storage()
    r.xreadgroup = AsyncMock(side_effect=ResponseError("some other error"))

    with pytest.raises(ResponseError):
        await storage.read_group("grp", "consumer1")


# ─── claim_pending() ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_claim_pending_no_pending_returns_empty():
    storage, r = _make_storage()
    r.xpending_range = AsyncMock(return_value=[])

    result = await storage.claim_pending("grp", "consumer1")

    assert result == []


@pytest.mark.asyncio
async def test_claim_pending_returns_claimed_messages():
    storage, r = _make_storage()
    r.xpending_range = AsyncMock(return_value=[
        {"message_id": "msg_1", "time_since_delivered": 60000},
    ])
    r.xclaim = AsyncMock(return_value=[
        ("msg_1", {"data": json.dumps({"id": "p1"})}),
    ])

    result = await storage.claim_pending("grp", "consumer1", min_idle_time_ms=30000)

    assert len(result) == 1
    assert result[0][0] == "msg_1"


@pytest.mark.asyncio
async def test_claim_pending_skips_not_idle_enough():
    storage, r = _make_storage()
    r.xpending_range = AsyncMock(return_value=[
        {"message_id": "msg_1", "time_since_delivered": 1000},  # too recent
    ])

    result = await storage.claim_pending("grp", "consumer1", min_idle_time_ms=30000)

    assert result == []


# ─── get_stream_length() ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_stream_length_returns_count():
    storage, r = _make_storage()
    r.xlen = AsyncMock(return_value=42)

    result = await storage.get_stream_length()

    assert result == 42


@pytest.mark.asyncio
async def test_get_stream_length_returns_zero_on_error():
    storage, r = _make_storage()
    r.xlen = AsyncMock(side_effect=ResponseError("no stream"))

    result = await storage.get_stream_length()

    assert result == 0


# ─── acknowledge() ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_acknowledge_calls_xack():
    storage, r = _make_storage()
    r.xack = AsyncMock(return_value=1)

    result = await storage.acknowledge("grp", "msg_1")

    assert result == 1
    r.xack.assert_called_once_with("test_stream", "grp", "msg_1")


@pytest.mark.asyncio
async def test_acknowledge_no_ids_returns_zero():
    storage, r = _make_storage()

    result = await storage.acknowledge("grp")

    assert result == 0


# ─── delete() ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_calls_xdel():
    storage, r = _make_storage()
    r.xdel = AsyncMock(return_value=1)

    result = await storage.delete("msg_1")

    assert result == 1


@pytest.mark.asyncio
async def test_delete_no_ids_returns_zero():
    storage, r = _make_storage()

    result = await storage.delete()

    assert result == 0


@pytest.mark.asyncio
async def test_delete_error_returns_zero():
    storage, r = _make_storage()
    r.xdel = AsyncMock(side_effect=Exception("Redis error"))

    result = await storage.delete("msg_1")

    assert result == 0


# ─── _deserialize_dict() ──────────────────────────────────────────────────────

def test_deserialize_dict_valid_json():
    storage, _ = _make_storage()
    result = storage._deserialize_dict({"key": '{"a": 1}'})
    assert result == {"key": {"a": 1}}


def test_deserialize_dict_raw_string_fallback():
    storage, _ = _make_storage()
    result = storage._deserialize_dict({"key": "not-json"})
    assert result == {"key": "not-json"}


def test_deserialize_dict_mixed():
    storage, _ = _make_storage()
    result = storage._deserialize_dict({"a": '"hello"', "b": "raw"})
    assert result["a"] == "hello"
    assert result["b"] == "raw"
