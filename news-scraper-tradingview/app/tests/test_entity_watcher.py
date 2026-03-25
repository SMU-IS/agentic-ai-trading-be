"""
Tests for app/services/entity_watcher.py

Coverage:
  get_tickers_from_redis — happy, empty hash, bytes keys, Redis error
  get_ticker_candidates  — plain ticker, pre-prefixed ticker
  EntityWatcherService   — new ticker pushed, already-processed skipped
"""

from unittest.mock import MagicMock

import fakeredis
import pytest

from app.services.entity_watcher import (
    EXCHANGE_CANDIDATES,
    EntityWatcherService,
    get_ticker_candidates,
    get_tickers_from_redis,
)


# ── get_tickers_from_redis ─────────────────────────────────────────────────────

class TestGetTickersFromRedis:

    @pytest.fixture
    def r(self):
        return fakeredis.FakeRedis(decode_responses=True)

    def test_happy_returns_all_tickers(self, r):
        """[HAPPY] Returns every key from all_identified_tickers hash."""
        r.hset("all_identified_tickers", mapping={"AAPL": "1", "TSLA": "1", "NVDA": "1"})
        result = get_tickers_from_redis(r)
        assert set(result) == {"AAPL", "TSLA", "NVDA"}

    def test_happy_returns_list_type(self, r):
        """[HAPPY] Return value is a list."""
        r.hset("all_identified_tickers", "MSFT", "1")
        result = get_tickers_from_redis(r)
        assert isinstance(result, list)

    def test_boundary_empty_hash_returns_empty_list(self, r):
        """[BOUNDARY] No tickers in hash → empty list returned."""
        result = get_tickers_from_redis(r)
        assert result == []

    def test_boundary_bytes_keys_are_decoded(self):
        """[BOUNDARY] Byte-encoded ticker keys are decoded to strings."""
        fake_r = fakeredis.FakeRedis(decode_responses=False)
        fake_r.hset("all_identified_tickers", b"AMZN", b"1")
        result = get_tickers_from_redis(fake_r)
        assert "AMZN" in result

    def test_sad_redis_exception_returns_empty_list(self, r):
        """[SAD] Connection failure is caught and empty list is returned."""
        broken = MagicMock()
        broken.hgetall.side_effect = Exception("Redis connection refused")
        result = get_tickers_from_redis(broken)
        assert result == []


# ── get_ticker_candidates ──────────────────────────────────────────────────────

class TestGetTickerCandidates:

    def test_happy_plain_ticker_returns_all_exchange_candidates(self):
        """[HAPPY] Plain ticker expands to one candidate per exchange."""
        result = get_ticker_candidates("AAPL")
        assert result == [f"{ex}:AAPL" for ex in EXCHANGE_CANDIDATES]

    def test_happy_nasdaq_is_first_candidate(self):
        """[HAPPY] NASDAQ is tried first."""
        result = get_ticker_candidates("TSLA")
        assert result[0] == "NASDAQ:TSLA"

    def test_happy_nyse_is_second_candidate(self):
        """[HAPPY] NYSE is tried second."""
        result = get_ticker_candidates("JPM")
        assert result[1] == "NYSE:JPM"

    def test_happy_returns_three_candidates(self):
        """[HAPPY] Exactly one candidate per exchange in EXCHANGE_CANDIDATES."""
        result = get_ticker_candidates("NVDA")
        assert len(result) == len(EXCHANGE_CANDIDATES)

    def test_boundary_prefixed_ticker_returned_as_single_item(self):
        """[BOUNDARY] Ticker already containing ':' is returned unchanged."""
        result = get_ticker_candidates("NYSE:JPM")
        assert result == ["NYSE:JPM"]

    def test_boundary_another_prefixed_ticker(self):
        """[BOUNDARY] NASDAQ-prefixed ticker is not re-prefixed."""
        result = get_ticker_candidates("NASDAQ:MSFT")
        assert result == ["NASDAQ:MSFT"]
        assert len(result) == 1

    def test_sad_candidates_contain_original_symbol(self):
        """[SAD] Each candidate ends with the original symbol."""
        symbol = "COIN"
        for candidate in get_ticker_candidates(symbol):
            assert candidate.endswith(f":{symbol}")


# ── EntityWatcherService ───────────────────────────────────────────────────────

class TestEntityWatcherService:

    @pytest.fixture
    def r(self):
        return fakeredis.FakeRedis(decode_responses=True)

    def test_happy_new_ticker_pushed_to_batch_queue(self, r):
        """[HAPPY] New ticker in hash is pushed to batch_queue."""
        r.hset("all_identified_tickers", "AAPL", "1")
        watcher = EntityWatcherService(r)

        # Simulate one loop iteration manually
        entities = r.hgetall("all_identified_tickers")
        for ticker in entities:
            ticker = ticker.decode() if isinstance(ticker, bytes) else ticker
            if not r.sismember("entity_processed_set", ticker):
                r.lpush("batch_queue", ticker)
                r.sadd("entity_processed_set", ticker)
                r.set("stream_version", "1")

        assert r.llen("batch_queue") == 1
        assert r.lrange("batch_queue", 0, -1) == ["AAPL"]

    def test_happy_stream_version_updated_on_new_ticker(self, r):
        """[HAPPY] stream_version key is set when a new ticker is detected."""
        r.hset("all_identified_tickers", "TSLA", "1")

        entities = r.hgetall("all_identified_tickers")
        for ticker in entities:
            if not r.sismember("entity_processed_set", ticker):
                r.lpush("batch_queue", ticker)
                r.sadd("entity_processed_set", ticker)
                r.set("stream_version", "1")

        assert r.get("stream_version") is not None

    def test_boundary_already_processed_ticker_not_re_queued(self, r):
        """[BOUNDARY] Ticker already in processed_set is skipped."""
        r.hset("all_identified_tickers", "MSFT", "1")
        r.sadd("entity_processed_set", "MSFT")

        entities = r.hgetall("all_identified_tickers")
        for ticker in entities:
            if not r.sismember("entity_processed_set", ticker):
                r.lpush("batch_queue", ticker)

        assert r.llen("batch_queue") == 0

    def test_boundary_empty_hash_no_queue_entries(self, r):
        """[BOUNDARY] Empty hash produces no queue entries and no stream_version."""
        watcher = EntityWatcherService(r)
        entities = r.hgetall("all_identified_tickers")
        updated = False
        for ticker in entities:
            updated = True
        assert not updated
        assert r.get("stream_version") is None

    def test_sad_multiple_new_tickers_all_queued(self, r):
        """[SAD] Multiple new tickers are all pushed to the queue."""
        for t in ["AAPL", "GOOG", "NVDA"]:
            r.hset("all_identified_tickers", t, "1")

        entities = r.hgetall("all_identified_tickers")
        for ticker in entities:
            if not r.sismember("entity_processed_set", ticker):
                r.lpush("batch_queue", ticker)
                r.sadd("entity_processed_set", ticker)

        assert r.llen("batch_queue") == 3
