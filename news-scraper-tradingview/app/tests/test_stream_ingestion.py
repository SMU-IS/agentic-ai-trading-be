"""
Tests for app/services/tradingview_minds_stream_ingestion.py
       and app/services/tradingview_ideas_stream_ingestion.py

Coverage:
  TradingViewMindsStreamIngestion:
    - Initial state
    - run(): publishes new items, layer-1 in-memory dedup,
             layer-2 Redis dedup, stops when _running=False,
             exception per ticker does not crash loop,
             in-memory cache pruned at MAX_MEMORY_CACHE

  TradingViewIdeasStreamIngestion:
    - Initial state
    - run(): same dedup and stop behaviour,
             skips items with empty dedup key
"""

from unittest.mock import MagicMock, patch

import fakeredis
import pytest

from app.services.tradingview_minds_stream_ingestion import TradingViewMindsStreamIngestion
from app.services.tradingview_ideas_stream_ingestion import TradingViewIdeasStreamIngestion


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _make_mind(uid="m001", text="Bull run incoming!", created="2026-03-15 10:00:00"):
    return {
        "uid": uid,
        "text": text,
        "created": created,
        "author": {"username": "trader1"},
        "url": "https://tradingview.com/u/trader1/",
        "total_likes": 5,
        "total_comments": 2,
        "symbols": ["NASDAQ:AAPL"],
    }


def _make_idea(author="analyst1", timestamp=1710000000, title="AAPL Setup"):
    return {
        "author": author,
        "timestamp": timestamp,
        "title": title,
        "description": "Technical breakout setup.",
        "chart_url": "https://tradingview.com/chart/AAPL/abc/",
        "likes_count": 10,
        "comments_count": 2,
        "views_count": 0,
        "preview_image": [],
    }


# ── TradingViewMindsStreamIngestion ────────────────────────────────────────────

class TestTradingViewMindsStreamIngestion:

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.r = fakeredis.FakeRedis(decode_responses=True)
        self.r.hset("all_identified_tickers", "AAPL", "1")
        self.ingestion = TradingViewMindsStreamIngestion(self.r)
        self.ingestion.scraper = MagicMock()

    # HAPPY PATH ---------------------------------------------------------------

    def test_happy_initial_state(self):
        """[HAPPY] Fresh instance starts with _running=True and empty cache."""
        assert self.ingestion._running is True
        assert len(self.ingestion.seen_in_memory) == 0

    @patch("app.services.tradingview_minds_stream_ingestion.time.sleep")
    def test_happy_run_publishes_new_item(self, mock_sleep):
        """[HAPPY] New mind is published to the Redis stream."""
        self.ingestion.scraper.get_minds.return_value = {
            "status": "success", "data": [_make_mind(uid="m001")]
        }
        mock_sleep.side_effect = lambda n: setattr(self.ingestion, "_running", False)
        self.ingestion.run()
        assert self.r.xlen("tradingview:minds:raw") == 1

    @patch("app.services.tradingview_minds_stream_ingestion.time.sleep")
    def test_happy_run_adds_to_in_memory_cache(self, mock_sleep):
        """[HAPPY] Published uid is added to seen_in_memory set."""
        self.ingestion.scraper.get_minds.return_value = {
            "status": "success", "data": [_make_mind(uid="m001")]
        }
        mock_sleep.side_effect = lambda n: setattr(self.ingestion, "_running", False)
        self.ingestion.run()
        assert "m001" in self.ingestion.seen_in_memory

    # BOUNDARY PATH ------------------------------------------------------------

    @patch("app.services.tradingview_minds_stream_ingestion.time.sleep")
    def test_boundary_layer1_dedup_in_memory(self, mock_sleep):
        """[BOUNDARY] Item in seen_in_memory is skipped without hitting Redis."""
        self.ingestion.seen_in_memory.add("m001")
        self.ingestion.scraper.get_minds.return_value = {
            "status": "success", "data": [_make_mind(uid="m001")]
        }
        mock_sleep.side_effect = lambda n: setattr(self.ingestion, "_running", False)
        self.ingestion.run()
        assert self.r.xlen("tradingview:minds:raw") == 0

    @patch("app.services.tradingview_minds_stream_ingestion.time.sleep")
    def test_boundary_layer2_dedup_redis(self, mock_sleep):
        """[BOUNDARY] Item already in Redis dedup store is skipped."""
        self.r.set("tradingview_minds:m001", 1)  # pre-mark as seen
        self.ingestion.scraper.get_minds.return_value = {
            "status": "success", "data": [_make_mind(uid="m001")]
        }
        mock_sleep.side_effect = lambda n: setattr(self.ingestion, "_running", False)
        self.ingestion.run()
        assert self.r.xlen("tradingview:minds:raw") == 0

    @patch("app.services.tradingview_minds_stream_ingestion.time.sleep")
    def test_boundary_stops_when_running_false(self, mock_sleep):
        """[BOUNDARY] Loop exits cleanly when _running is set to False."""
        self.ingestion.scraper.get_minds.return_value = {
            "status": "success", "data": []
        }
        mock_sleep.side_effect = lambda n: setattr(self.ingestion, "_running", False)
        self.ingestion.run()  # must not hang
        assert self.ingestion._running is False

    @patch("app.services.tradingview_minds_stream_ingestion.time.sleep")
    def test_boundary_memory_cache_pruned_at_max(self, mock_sleep):
        """[BOUNDARY] seen_in_memory is cleared when MAX_MEMORY_CACHE is exceeded."""
        self.ingestion.seen_in_memory = set(
            str(i) for i in range(TradingViewMindsStreamIngestion.MAX_MEMORY_CACHE + 1)
        )
        self.ingestion.scraper.get_minds.return_value = {
            "status": "success", "data": []
        }
        mock_sleep.side_effect = lambda n: setattr(self.ingestion, "_running", False)
        self.ingestion.run()
        assert len(self.ingestion.seen_in_memory) == 0

    # SAD PATH -----------------------------------------------------------------

    @patch("app.services.tradingview_minds_stream_ingestion.time.sleep")
    def test_sad_exception_per_ticker_does_not_crash_loop(self, mock_sleep):
        """[SAD] Exception while scraping a ticker is caught; loop continues."""
        self.ingestion.scraper.get_minds.side_effect = Exception("TradingView 503")
        mock_sleep.side_effect = lambda n: setattr(self.ingestion, "_running", False)
        self.ingestion.run()  # must not raise
        assert self.r.xlen("tradingview:minds:raw") == 0

    @patch("app.services.tradingview_minds_stream_ingestion.time.sleep")
    def test_sad_non_success_status_skips_ticker(self, mock_sleep):
        """[SAD] Non-success API response is silently skipped."""
        self.ingestion.scraper.get_minds.return_value = {"status": "failed", "data": []}
        mock_sleep.side_effect = lambda n: setattr(self.ingestion, "_running", False)
        self.ingestion.run()
        assert self.r.xlen("tradingview:minds:raw") == 0


# ── TradingViewIdeasStreamIngestion ────────────────────────────────────────────

class TestTradingViewIdeasStreamIngestion:

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.r = fakeredis.FakeRedis(decode_responses=True)
        self.r.hset("all_identified_tickers", "AAPL", "1")
        self.ingestion = TradingViewIdeasStreamIngestion(self.r)
        self.ingestion.scraper = MagicMock()

    # HAPPY PATH ---------------------------------------------------------------

    def test_happy_initial_state(self):
        """[HAPPY] Fresh instance starts with _running=True and empty cache."""
        assert self.ingestion._running is True
        assert len(self.ingestion.seen_in_memory) == 0

    @patch("app.services.tradingview_ideas_stream_ingestion.time.sleep")
    def test_happy_run_publishes_new_idea(self, mock_sleep):
        """[HAPPY] New idea is published to the Redis stream."""
        self.ingestion.scraper.scrape.return_value = [_make_idea()]
        mock_sleep.side_effect = lambda n: setattr(self.ingestion, "_running", False)
        self.ingestion.run()
        assert self.r.xlen("tradingview:ideas:raw") == 1

    @patch("app.services.tradingview_ideas_stream_ingestion.time.sleep")
    def test_happy_run_adds_to_in_memory_cache(self, mock_sleep):
        """[HAPPY] Dedup key of published idea is added to seen_in_memory."""
        idea = _make_idea(author="u1", timestamp=100, title="Setup")
        self.ingestion.scraper.scrape.return_value = [idea]
        mock_sleep.side_effect = lambda n: setattr(self.ingestion, "_running", False)
        self.ingestion.run()
        expected_key = "u1:100:Setup"
        assert expected_key in self.ingestion.seen_in_memory

    # BOUNDARY PATH ------------------------------------------------------------

    @patch("app.services.tradingview_ideas_stream_ingestion.time.sleep")
    def test_boundary_layer1_dedup_in_memory(self, mock_sleep):
        """[BOUNDARY] Idea already in seen_in_memory is counted as duplicate."""
        idea = _make_idea(author="u1", timestamp=100, title="Setup")
        dedup_key = "u1:100:Setup"
        self.ingestion.seen_in_memory.add(dedup_key)
        self.ingestion.scraper.scrape.return_value = [idea]
        mock_sleep.side_effect = lambda n: setattr(self.ingestion, "_running", False)
        self.ingestion.run()
        assert self.r.xlen("tradingview:ideas:raw") == 0

    @patch("app.services.tradingview_ideas_stream_ingestion.time.sleep")
    def test_boundary_layer2_dedup_redis(self, mock_sleep):
        """[BOUNDARY] Idea already in Redis dedup store is skipped."""
        self.r.set("tradingview_ideas:u1:100:Setup", 1)
        self.ingestion.scraper.scrape.return_value = [
            _make_idea(author="u1", timestamp=100, title="Setup")
        ]
        mock_sleep.side_effect = lambda n: setattr(self.ingestion, "_running", False)
        self.ingestion.run()
        assert self.r.xlen("tradingview:ideas:raw") == 0

    @patch("app.services.tradingview_ideas_stream_ingestion.time.sleep")
    def test_boundary_skips_idea_with_empty_dedup_key(self, mock_sleep):
        """[BOUNDARY] Idea with all-default fields ('unknown::') is skipped."""
        self.ingestion.scraper.scrape.return_value = [{}]  # empty dict → unknown::
        mock_sleep.side_effect = lambda n: setattr(self.ingestion, "_running", False)
        self.ingestion.run()
        assert self.r.xlen("tradingview:ideas:raw") == 0

    @patch("app.services.tradingview_ideas_stream_ingestion.time.sleep")
    def test_boundary_stops_when_running_false(self, mock_sleep):
        """[BOUNDARY] Loop exits cleanly when _running is set to False."""
        self.ingestion.scraper.scrape.return_value = []
        mock_sleep.side_effect = lambda n: setattr(self.ingestion, "_running", False)
        self.ingestion.run()
        assert self.ingestion._running is False

    @patch("app.services.tradingview_ideas_stream_ingestion.time.sleep")
    def test_boundary_non_list_result_skipped(self, mock_sleep):
        """[BOUNDARY] Unexpected non-list response is skipped without error."""
        self.ingestion.scraper.scrape.return_value = {"error": "bad"}
        mock_sleep.side_effect = lambda n: setattr(self.ingestion, "_running", False)
        self.ingestion.run()  # must not raise
        assert self.r.xlen("tradingview:ideas:raw") == 0

    # SAD PATH -----------------------------------------------------------------

    @patch("app.services.tradingview_ideas_stream_ingestion.time.sleep")
    def test_sad_exception_does_not_crash_loop(self, mock_sleep):
        """[SAD] Exception while scraping is caught; loop continues."""
        self.ingestion.scraper.scrape.side_effect = Exception("Network failure")
        mock_sleep.side_effect = lambda n: setattr(self.ingestion, "_running", False)
        self.ingestion.run()  # must not raise

    @patch("app.services.tradingview_ideas_stream_ingestion.time.sleep")
    def test_sad_memory_cache_pruned_at_max(self, mock_sleep):
        """[SAD] seen_in_memory is cleared when MAX_MEMORY_CACHE is exceeded."""
        self.ingestion.seen_in_memory = set(
            str(i) for i in range(TradingViewIdeasStreamIngestion.MAX_MEMORY_CACHE + 1)
        )
        self.ingestion.scraper.scrape.return_value = []
        mock_sleep.side_effect = lambda n: setattr(self.ingestion, "_running", False)
        self.ingestion.run()
        assert len(self.ingestion.seen_in_memory) == 0
