"""
Tests for app/services/storage.py

Coverage:
  RedisStreamStorage  — save, save_batch
  publish_to_stream   — serialisation, stream key, non-ASCII
  check_and_mark_seen — new key, seen key, TTL behaviour
  get_redis_client    — uses env_config values
"""

import json
from unittest.mock import MagicMock, patch

import fakeredis
import pytest

from app.services.storage import (
    RedisStreamStorage,
    check_and_mark_seen,
    get_redis_client,
    publish_to_stream,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_storage(stream_name="tradingview:minds:raw"):
    fake_r = fakeredis.FakeRedis(decode_responses=True)
    s = RedisStreamStorage.__new__(RedisStreamStorage)
    s.r = fake_r
    s.stream_name = stream_name
    return s, fake_r


# ── RedisStreamStorage ─────────────────────────────────────────────────────────

class TestRedisStreamStorage:

    # HAPPY PATH ---------------------------------------------------------------

    def test_happy_save_writes_to_stream(self):
        """[HAPPY] save() writes one JSON-encoded entry to the configured stream."""
        storage, r = _make_storage()
        storage.save({"id": "tradingview_minds:abc", "content_type": "mind"})
        entries = r.xrange("tradingview:minds:raw")
        assert len(entries) == 1
        assert json.loads(entries[0][1]["data"])["id"] == "tradingview_minds:abc"

    def test_happy_save_batch_all_items_present(self):
        """[HAPPY] save_batch() writes every item to the stream."""
        storage, r = _make_storage("tradingview:ideas:raw")
        items = [{"id": f"tradingview_ideas:{i}"} for i in range(10)]
        storage.save_batch(items)
        assert len(r.xrange("tradingview:ideas:raw")) == 10

    def test_happy_save_batch_order_preserved(self):
        """[HAPPY] Items appear in insertion order inside the stream."""
        storage, r = _make_storage()
        items = [{"id": f"mind:{i}", "seq": i} for i in range(5)]
        storage.save_batch(items)
        for i, entry in enumerate(r.xrange("tradingview:minds:raw")):
            assert json.loads(entry[1]["data"])["seq"] == i

    # BOUNDARY PATH ------------------------------------------------------------

    def test_boundary_save_batch_empty_list_writes_nothing(self):
        """[BOUNDARY] Empty list leaves the stream empty."""
        storage, r = _make_storage()
        storage.save_batch([])
        assert len(r.xrange("tradingview:minds:raw")) == 0

    def test_boundary_custom_stream_name_directs_writes(self):
        """[BOUNDARY] Changing stream_name writes to that key only."""
        storage, r = _make_storage("tradingview:minds:raw")
        storage.stream_name = "tradingview:ideas:raw"
        storage.save({"id": "idea:1"})
        assert r.xlen("tradingview:ideas:raw") == 1
        assert r.xlen("tradingview:minds:raw") == 0

    def test_boundary_save_batch_single_item(self):
        """[BOUNDARY] Batch of one item behaves identically to save()."""
        storage, r = _make_storage()
        storage.save_batch([{"id": "mind:single"}])
        entries = r.xrange("tradingview:minds:raw")
        assert len(entries) == 1
        assert json.loads(entries[0][1]["data"])["id"] == "mind:single"

    # SAD PATH -----------------------------------------------------------------

    def test_sad_non_ascii_content_preserved(self):
        """[SAD] Non-ASCII characters survive JSON serialisation round-trip."""
        storage, r = _make_storage()
        storage.save({"text": "株式市場テスト"})
        entry = r.xrange("tradingview:minds:raw")[0]
        assert json.loads(entry[1]["data"])["text"] == "株式市場テスト"


# ── publish_to_stream ──────────────────────────────────────────────────────────

class TestPublishToStream:

    @pytest.fixture
    def r(self):
        return fakeredis.FakeRedis(decode_responses=True)

    def test_happy_publishes_serialised_json(self, r):
        """[HAPPY] Item is JSON-encoded and pushed to the stream."""
        item = {"id": "tradingview_minds:uid1", "content_type": "mind"}
        publish_to_stream(r, "tradingview:minds:raw", item)
        entries = r.xrange("tradingview:minds:raw")
        assert len(entries) == 1
        assert json.loads(entries[0][1]["data"])["id"] == "tradingview_minds:uid1"

    def test_happy_nested_dict_round_trips(self, r):
        """[HAPPY] Nested content dict is intact after publish."""
        item = {"content": {"title": "AAPL rally", "body": "Big move today"}}
        publish_to_stream(r, "tradingview:ideas:raw", item)
        payload = json.loads(r.xrange("tradingview:ideas:raw")[0][1]["data"])
        assert payload["content"]["title"] == "AAPL rally"

    def test_boundary_non_ascii_preserved(self, r):
        """[BOUNDARY] Non-ASCII text is stored without escaping."""
        item = {"text": "日本語テスト"}
        publish_to_stream(r, "test:stream", item)
        payload = r.xrange("test:stream")[0][1]["data"]
        assert "日本語テスト" in payload

    def test_boundary_empty_dict_published(self, r):
        """[BOUNDARY] Empty dict is published without error."""
        publish_to_stream(r, "test:stream", {})
        assert r.xlen("test:stream") == 1


# ── check_and_mark_seen ────────────────────────────────────────────────────────

class TestCheckAndMarkSeen:

    @pytest.fixture
    def r(self):
        return fakeredis.FakeRedis(decode_responses=True)

    def test_happy_new_key_returns_false(self, r):
        """[HAPPY] Unseen key returns False (not a duplicate)."""
        result = check_and_mark_seen(r, "uid001", "tradingview_minds")
        assert result is False

    def test_happy_seen_key_returns_true(self, r):
        """[HAPPY] Same key on second call returns True (duplicate)."""
        check_and_mark_seen(r, "uid001", "tradingview_minds")
        result = check_and_mark_seen(r, "uid001", "tradingview_minds")
        assert result is True

    def test_happy_new_key_is_persisted(self, r):
        """[HAPPY] After marking, the key exists in Redis."""
        check_and_mark_seen(r, "uid001", "tradingview_minds")
        assert r.exists("tradingview_minds:uid001") == 1

    def test_boundary_redis_key_format_correct(self, r):
        """[BOUNDARY] Redis key is '{set_name}:{key}'."""
        check_and_mark_seen(r, "author:1234:title", "tradingview_ideas")
        assert r.exists("tradingview_ideas:author:1234:title") == 1

    def test_boundary_with_ttl_key_has_expiry(self, r):
        """[BOUNDARY] ttl_days=3 sets a TTL on the Redis key."""
        check_and_mark_seen(r, "uid002", "tradingview_minds", ttl_days=3)
        ttl = r.ttl("tradingview_minds:uid002")
        assert 0 < ttl <= 3 * 86400

    def test_boundary_without_ttl_key_is_permanent(self, r):
        """[BOUNDARY] Default (no TTL) stores key with no expiry (-1)."""
        check_and_mark_seen(r, "uid003", "tradingview_minds")
        assert r.ttl("tradingview_minds:uid003") == -1

    def test_sad_different_set_names_are_independent(self, r):
        """[SAD] Same key in different set_names are independent."""
        check_and_mark_seen(r, "uid001", "tradingview_minds")
        result = check_and_mark_seen(r, "uid001", "tradingview_ideas")
        assert result is False  # different namespace


# ── get_redis_client ───────────────────────────────────────────────────────────

class TestGetRedisClient:

    def test_happy_returns_redis_instance(self):
        """[HAPPY] Returns a Redis client object."""
        with patch("app.services.storage.redis.Redis") as mock_cls:
            mock_cls.return_value = MagicMock()
            client = get_redis_client()
            mock_cls.assert_called_once()
            assert client is mock_cls.return_value

    def test_happy_uses_config_host_and_port(self):
        """[HAPPY] Client is constructed with host/port from env_config."""
        with patch("app.services.storage.redis.Redis") as mock_cls:
            with patch("app.services.storage.env_config") as mock_cfg:
                mock_cfg.redis_host = "cloud-host.redis.com"
                mock_cfg.redis_port = 17989
                mock_cfg.redis_password = "secret"
                get_redis_client()
                kwargs = mock_cls.call_args[1]
                assert kwargs["host"] == "cloud-host.redis.com"
                assert kwargs["port"] == 17989
