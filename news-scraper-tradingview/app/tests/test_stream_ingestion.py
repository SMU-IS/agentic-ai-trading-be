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

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import fakeredis
import pytest

from app.services.tradingview_minds_stream_ingestion import TradingViewMindsStreamIngestion
from app.services.tradingview_ideas_stream_ingestion import TradingViewIdeasStreamIngestion

# Recent timestamp (within 15-min bootstrap window)
_RECENT_UTC = datetime.now(timezone.utc) - timedelta(minutes=2)
_RECENT_CREATED = _RECENT_UTC.strftime("%Y-%m-%d %H:%M:%S")
_RECENT_EPOCH = int(_RECENT_UTC.timestamp())

# Old timestamp (outside bootstrap window)
_OLD_UTC = datetime.now(timezone.utc) - timedelta(hours=2)
_OLD_CREATED = _OLD_UTC.strftime("%Y-%m-%d %H:%M:%S")
_OLD_EPOCH = int(_OLD_UTC.timestamp())


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _make_mind(uid="m001", text="Bull run incoming!", created=None):
    return {
        "uid": uid,
        "text": text,
        "created": created or _RECENT_CREATED,
        "author": {"username": "trader1"},
        "url": "https://tradingview.com/u/trader1/",
        "total_likes": 5,
        "total_comments": 2,
        "symbols": ["NASDAQ:AAPL"],
    }


def _make_idea(author="analyst1", timestamp=None, title="AAPL Setup"):
    return {
        "author": author,
        "timestamp": timestamp if timestamp is not None else _RECENT_EPOCH,
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
        patcher = patch(
            "app.services.tradingview_minds_stream_ingestion.get_tickers_from_redis",
            return_value=["AAPL"],
        )
        patcher.start()
        self.ingestion = TradingViewMindsStreamIngestion(self.r)
        self.ingestion.scraper = MagicMock()
        yield
        patcher.stop()

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
        assert self.r.xlen("raw_news_stream") == 1

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
        assert self.r.xlen("raw_news_stream") == 0

    @patch("app.services.tradingview_minds_stream_ingestion.time.sleep")
    def test_boundary_layer2_dedup_redis(self, mock_sleep):
        """[BOUNDARY] Item already in Redis dedup store is skipped."""
        self.r.set("tradingview_minds:m001", 1)  # pre-mark as seen
        self.ingestion.scraper.get_minds.return_value = {
            "status": "success", "data": [_make_mind(uid="m001")]
        }
        mock_sleep.side_effect = lambda n: setattr(self.ingestion, "_running", False)
        self.ingestion.run()
        assert self.r.xlen("raw_news_stream") == 0

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
        assert self.r.xlen("raw_news_stream") == 0

    @patch("app.services.tradingview_minds_stream_ingestion.time.sleep")
    def test_sad_non_success_status_skips_ticker(self, mock_sleep):
        """[SAD] Non-success API response is silently skipped."""
        self.ingestion.scraper.get_minds.return_value = {"status": "failed", "data": []}
        mock_sleep.side_effect = lambda n: setattr(self.ingestion, "_running", False)
        self.ingestion.run()
        assert self.r.xlen("raw_news_stream") == 0

    @patch("app.services.tradingview_minds_stream_ingestion.time.sleep")
    def test_boundary_layer3_preproc_dedup(self, mock_sleep):
        """[BOUNDARY] Item with preproc_dedup key but no other dedup key is skipped."""
        self.r.set("preproc_dedup:m001", "1")
        self.ingestion.scraper.get_minds.return_value = {
            "status": "success", "data": [_make_mind(uid="m001")]
        }
        mock_sleep.side_effect = lambda n: setattr(self.ingestion, "_running", False)
        self.ingestion.run()
        assert self.r.xlen("raw_news_stream") == 0

    # HWM (high-water mark) ---------------------------------------------------

    @patch("app.services.tradingview_minds_stream_ingestion.time.sleep")
    def test_happy_old_post_filtered_by_hwm(self, mock_sleep):
        """[HAPPY] Post older than bootstrap window is skipped."""
        self.ingestion.scraper.get_minds.return_value = {
            "status": "success", "data": [_make_mind(uid="old1", created=_OLD_CREATED)]
        }
        mock_sleep.side_effect = lambda n: setattr(self.ingestion, "_running", False)
        self.ingestion.run()
        assert self.r.xlen("raw_news_stream") == 0

    @patch("app.services.tradingview_minds_stream_ingestion.time.sleep")
    def test_happy_hwm_updated_after_cycle(self, mock_sleep):
        """[HAPPY] HWM is written to Redis after processing a ticker."""
        self.ingestion.scraper.get_minds.return_value = {
            "status": "success", "data": [_make_mind(uid="m001")]
        }
        mock_sleep.side_effect = lambda n: setattr(self.ingestion, "_running", False)
        self.ingestion.run()
        hwm_val = self.r.get("hwm:tradingview_minds:AAPL")
        assert hwm_val is not None

    @patch("app.services.tradingview_minds_stream_ingestion.time.sleep")
    def test_happy_hwm_prevents_re_ingestion(self, mock_sleep):
        """[HAPPY] After HWM is set, same-timestamp post is not re-ingested."""
        mind = _make_mind(uid="m001")
        self.ingestion.scraper.get_minds.return_value = {
            "status": "success", "data": [mind]
        }
        # First cycle: publishes the post and sets HWM
        call_count = [0]
        def stop_after_two(n):
            call_count[0] += 1
            if call_count[0] >= 3:
                self.ingestion._running = False
        mock_sleep.side_effect = stop_after_two
        self.ingestion.run()
        # Post published once (first cycle), not again on second cycle
        assert self.r.xlen("raw_news_stream") == 1


# ── TradingViewIdeasStreamIngestion ────────────────────────────────────────────

class TestTradingViewIdeasStreamIngestion:

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.r = fakeredis.FakeRedis(decode_responses=True)
        patcher = patch(
            "app.services.tradingview_ideas_stream_ingestion.get_tickers_from_redis",
            return_value=["AAPL"],
        )
        patcher.start()
        self.ingestion = TradingViewIdeasStreamIngestion(self.r)
        self.ingestion.scraper = MagicMock()
        yield
        patcher.stop()

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
        assert self.r.xlen("raw_news_stream") == 1

    @patch("app.services.tradingview_ideas_stream_ingestion.time.sleep")
    def test_happy_run_adds_to_in_memory_cache(self, mock_sleep):
        """[HAPPY] Dedup key of published idea is added to seen_in_memory."""
        idea = _make_idea(author="u1", timestamp=_RECENT_EPOCH, title="Setup")
        self.ingestion.scraper.scrape.return_value = [idea]
        mock_sleep.side_effect = lambda n: setattr(self.ingestion, "_running", False)
        self.ingestion.run()
        expected_key = f"u1:{_RECENT_EPOCH}:Setup"
        assert expected_key in self.ingestion.seen_in_memory

    # BOUNDARY PATH ------------------------------------------------------------

    @patch("app.services.tradingview_ideas_stream_ingestion.time.sleep")
    def test_boundary_layer1_dedup_in_memory(self, mock_sleep):
        """[BOUNDARY] Idea already in seen_in_memory is counted as duplicate."""
        idea = _make_idea(author="u1", timestamp=_RECENT_EPOCH, title="Setup")
        dedup_key = f"u1:{_RECENT_EPOCH}:Setup"
        self.ingestion.seen_in_memory.add(dedup_key)
        self.ingestion.scraper.scrape.return_value = [idea]
        mock_sleep.side_effect = lambda n: setattr(self.ingestion, "_running", False)
        self.ingestion.run()
        assert self.r.xlen("raw_news_stream") == 0

    @patch("app.services.tradingview_ideas_stream_ingestion.time.sleep")
    def test_boundary_layer2_dedup_redis(self, mock_sleep):
        """[BOUNDARY] Idea already in Redis dedup store is skipped."""
        self.r.set(f"tradingview_ideas:u1:{_RECENT_EPOCH}:Setup", 1)
        self.ingestion.scraper.scrape.return_value = [
            _make_idea(author="u1", timestamp=_RECENT_EPOCH, title="Setup")
        ]
        mock_sleep.side_effect = lambda n: setattr(self.ingestion, "_running", False)
        self.ingestion.run()
        assert self.r.xlen("raw_news_stream") == 0

    @patch("app.services.tradingview_ideas_stream_ingestion.time.sleep")
    def test_boundary_skips_idea_with_empty_dedup_key(self, mock_sleep):
        """[BOUNDARY] Idea with all-default fields ('unknown::') is skipped."""
        self.ingestion.scraper.scrape.return_value = [{}]  # empty dict → unknown::
        mock_sleep.side_effect = lambda n: setattr(self.ingestion, "_running", False)
        self.ingestion.run()
        assert self.r.xlen("raw_news_stream") == 0

    @patch("app.services.tradingview_ideas_stream_ingestion.time.sleep")
    def test_boundary_layer3_preproc_dedup(self, mock_sleep):
        """[BOUNDARY] Idea with preproc_dedup key but no other dedup key is skipped."""
        idea = _make_idea(author="u1", timestamp=_RECENT_EPOCH, title="Setup")
        dedup_key = f"u1:{_RECENT_EPOCH}:Setup"
        self.r.set(f"preproc_dedup:{dedup_key}", "1")
        self.ingestion.scraper.scrape.return_value = [idea]
        mock_sleep.side_effect = lambda n: setattr(self.ingestion, "_running", False)
        self.ingestion.run()
        assert self.r.xlen("raw_news_stream") == 0

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
        assert self.r.xlen("raw_news_stream") == 0

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

    # HWM (high-water mark) ---------------------------------------------------

    @patch("app.services.tradingview_ideas_stream_ingestion.time.sleep")
    def test_happy_old_idea_filtered_by_hwm(self, mock_sleep):
        """[HAPPY] Idea older than bootstrap window is skipped."""
        self.ingestion.scraper.scrape.return_value = [
            _make_idea(author="old_u", timestamp=_OLD_EPOCH, title="Old Idea")
        ]
        mock_sleep.side_effect = lambda n: setattr(self.ingestion, "_running", False)
        self.ingestion.run()
        assert self.r.xlen("raw_news_stream") == 0

    @patch("app.services.tradingview_ideas_stream_ingestion.time.sleep")
    def test_happy_hwm_updated_after_cycle(self, mock_sleep):
        """[HAPPY] HWM is written to Redis after processing a ticker."""
        self.ingestion.scraper.scrape.return_value = [_make_idea()]
        mock_sleep.side_effect = lambda n: setattr(self.ingestion, "_running", False)
        self.ingestion.run()
        hwm_val = self.r.get("hwm:tradingview_ideas:AAPL")
        assert hwm_val is not None
