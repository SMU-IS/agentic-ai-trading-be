"""
Tests for app/services/tradingview_ideas_batch_ingestion.py

Coverage:
  _dedup_key   — author:timestamp:title key format, missing fields
  _build_row   — schema structure, timestamp conversion, fallback
  run()        — publishes new items, skips duplicates, handles errors,
                 respects ITEMS_PER_TICKER, empty ticker list
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import fakeredis
import pytest

from app.services.tradingview_ideas_batch_ingestion import TradingViewIdeasBatchIngestion

# Tickers the tests control — mirrors what get_tickers_from_redis would return
_TEST_TICKERS = ["AAPL", "TSLA"]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_idea(
    author="analyst1",
    timestamp=1710000000,
    title="AAPL Breakout Setup",
    description="Technical analysis of AAPL showing a bullish pattern.",
    chart_url="https://www.tradingview.com/chart/AAPL/abc123/",
    likes_count=42,
    comments_count=8,
    views_count=0,
    preview_image=None,
):
    return {
        "author": author,
        "timestamp": timestamp,
        "title": title,
        "description": description,
        "chart_url": chart_url,
        "likes_count": likes_count,
        "comments_count": comments_count,
        "views_count": views_count,
        "preview_image": preview_image or ["https://s3-symbol-logo.tradingview.com/apple.svg"],
    }


class TestTradingViewIdeasBatchIngestion:

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.r = fakeredis.FakeRedis(decode_responses=True)
        patcher = patch(
            "app.services.tradingview_ideas_batch_ingestion.get_tickers_from_redis",
            return_value=list(_TEST_TICKERS),
        )
        self.mock_get_tickers = patcher.start()
        self.ingestion = TradingViewIdeasBatchIngestion(self.r)
        self.ingestion.scraper = MagicMock()
        yield
        patcher.stop()

    # ── _dedup_key ─────────────────────────────────────────────────────────────

    def test_happy_dedup_key_format(self):
        """[HAPPY] Dedup key is '{author}:{timestamp}:{title}'."""
        idea = _make_idea(author="trader1", timestamp=1710000000, title="Bullish AAPL")
        key = TradingViewIdeasBatchIngestion._dedup_key(idea)
        assert key == "trader1:1710000000:Bullish AAPL"

    def test_boundary_dedup_key_missing_fields_uses_defaults(self):
        """[BOUNDARY] Missing fields fall back to 'unknown' and empty strings."""
        key = TradingViewIdeasBatchIngestion._dedup_key({})
        assert key == "unknown::"

    # ── _build_row ─────────────────────────────────────────────────────────────

    def test_happy_build_row_schema_structure(self):
        """[HAPPY] Built row contains all required top-level keys."""
        idea = _make_idea()
        row = TradingViewIdeasBatchIngestion._build_row(idea, "AAPL")
        for key in ("id", "content_type", "native_id", "source", "author",
                    "url", "timestamps", "content", "engagement", "metadata"):
            assert key in row, f"Missing key: {key}"

    def test_happy_build_row_content_type_is_idea(self):
        """[HAPPY] content_type is always 'idea'."""
        row = TradingViewIdeasBatchIngestion._build_row(_make_idea(), "AAPL")
        assert row["content_type"] == "idea"

    def test_happy_build_row_source_label(self):
        """[HAPPY] source defaults to 'tradingview_ideas_batch'."""
        row = TradingViewIdeasBatchIngestion._build_row(_make_idea(), "AAPL")
        assert row["source"] == "tradingview_ideas_batch"

    def test_happy_build_row_timestamp_converted_to_iso(self):
        """[HAPPY] Unix timestamp is converted to ISO-8601 string."""
        idea = _make_idea(timestamp=1710000000)
        row = TradingViewIdeasBatchIngestion._build_row(idea, "AAPL")
        expected = datetime.fromtimestamp(1710000000, tz=timezone.utc).isoformat()
        assert row["timestamps"] == expected

    def test_happy_build_row_content_fields(self):
        """[HAPPY] content.title and content.body are populated from idea."""
        idea = _make_idea(title="AAPL Setup", description="Strong support here.")
        row = TradingViewIdeasBatchIngestion._build_row(idea, "AAPL")
        assert row["content"]["title"] == "AAPL Setup"
        assert row["content"]["body"] == "Strong support here."

    def test_happy_build_row_engagement_fields(self):
        """[HAPPY] engagement contains total_comments, score, upvote_ratio."""
        idea = _make_idea(likes_count=10, comments_count=3)
        row = TradingViewIdeasBatchIngestion._build_row(idea, "AAPL")
        assert row["engagement"]["score"] == 10
        assert row["engagement"]["total_comments"] == 3
        assert row["engagement"]["upvote_ratio"] is None

    def test_happy_build_row_metadata_ticker(self):
        """[HAPPY] metadata.ticker holds the passed ticker symbol."""
        row = TradingViewIdeasBatchIngestion._build_row(_make_idea(), "TSLA")
        assert row["metadata"]["ticker"] == "TSLA"

    def test_boundary_build_row_invalid_timestamp_falls_back(self):
        """[BOUNDARY] Non-numeric timestamp falls back to current UTC time."""
        idea = _make_idea(timestamp="not-a-number")
        row = TradingViewIdeasBatchIngestion._build_row(idea, "AAPL")
        assert "T" in row["timestamps"]  # ISO format contains 'T'

    # ── run() ─────────────────────────────────────────────────────────────────

    @patch("app.services.tradingview_ideas_batch_ingestion.time.sleep", return_value=None)
    def test_happy_run_publishes_new_items(self, _sleep):
        """[HAPPY] New ideas are published to the Redis stream."""
        # Use distinct dedup keys per ticker so cross-ticker dedup doesn't reduce count
        ideas_aapl = [_make_idea(author=f"aapl_u{i}", timestamp=i, title=f"Idea A{i}") for i in range(3)]
        ideas_tsla = [_make_idea(author=f"tsla_u{i}", timestamp=i, title=f"Idea B{i}") for i in range(3)]
        self.ingestion.scraper.scrape.side_effect = [ideas_aapl, ideas_tsla]

        summary = self.ingestion.run()

        assert summary["total_published"] == 6   # 3 ideas × 2 tickers
        assert summary["total_duplicates"] == 0
        assert summary["errors"] == []
        assert self.r.xlen("raw_news_stream") == 6

    @patch("app.services.tradingview_ideas_batch_ingestion.time.sleep", return_value=None)
    def test_happy_run_skips_duplicates(self, _sleep):
        """[HAPPY] Same ideas on second run are detected as duplicates."""
        ideas = [_make_idea(author="user1", timestamp=100, title="AAPL Setup")]
        self.ingestion.scraper.scrape.return_value = ideas

        self.ingestion.run()
        summary2 = self.ingestion.run()

        assert summary2["total_published"] == 0
        assert summary2["total_duplicates"] == 2   # 1 idea × 2 tickers

    @patch("app.services.tradingview_ideas_batch_ingestion.time.sleep", return_value=None)
    def test_happy_run_summary_counts(self, _sleep):
        """[HAPPY] Summary reports correct tickers_processed and totals."""
        self.ingestion.scraper.scrape.return_value = [_make_idea()]
        summary = self.ingestion.run()
        assert summary["tickers_processed"] == 2
        assert summary["source"] == "tradingview_ideas_batch"

    @patch("app.services.tradingview_ideas_batch_ingestion.time.sleep", return_value=None)
    def test_boundary_empty_ticker_list(self, _sleep):
        """[BOUNDARY] No tickers → nothing scraped, zero counts."""
        self.mock_get_tickers.return_value = []
        summary = self.ingestion.run()
        assert summary["tickers_processed"] == 0
        assert summary["total_scraped"] == 0
        assert summary["total_published"] == 0

    @patch("app.services.tradingview_ideas_batch_ingestion.time.sleep", return_value=None)
    def test_boundary_respects_items_per_ticker_limit(self, _sleep):
        """[BOUNDARY] Only up to ITEMS_PER_TICKER items taken per ticker."""
        limit = TradingViewIdeasBatchIngestion.ITEMS_PER_TICKER
        # Use distinct dedup keys per ticker to avoid cross-ticker deduplication
        many_aapl = [_make_idea(author=f"a{i}", timestamp=i, title=f"AAPL Idea {i}") for i in range(50)]
        many_tsla = [_make_idea(author=f"t{i}", timestamp=i, title=f"TSLA Idea {i}") for i in range(50)]
        self.ingestion.scraper.scrape.side_effect = [many_aapl, many_tsla]
        self.ingestion.run()
        published = self.r.xlen("raw_news_stream")
        assert published == limit * 2  # 2 tickers

    @patch("app.services.tradingview_ideas_batch_ingestion.time.sleep", return_value=None)
    def test_boundary_skips_ideas_with_empty_dedup_key(self, _sleep):
        """[BOUNDARY] Ideas with empty dedup key ('unknown::') are skipped."""
        self.ingestion.scraper.scrape.return_value = [{}]  # all fields missing
        summary = self.ingestion.run()
        assert summary["total_published"] == 0

    @patch("app.services.tradingview_ideas_batch_ingestion.time.sleep", return_value=None)
    def test_sad_non_list_result_recorded_as_error(self, _sleep):
        """[SAD] Non-list scraper response is recorded in errors, not published."""
        self.ingestion.scraper.scrape.return_value = {"error": "unexpected"}
        summary = self.ingestion.run()
        assert summary["total_published"] == 0
        assert len(summary["errors"]) == 2   # one per ticker

    @patch("app.services.tradingview_ideas_batch_ingestion.time.sleep", return_value=None)
    def test_sad_scraper_exception_recorded_and_continues(self, _sleep):
        """[SAD] Exception on one ticker is recorded; other tickers still processed."""
        self.ingestion.scraper.scrape.side_effect = [
            Exception("TradingView timeout"),
            [_make_idea()],
        ]
        summary = self.ingestion.run()
        assert len(summary["errors"]) == 1
        assert summary["total_published"] == 1

    @patch("app.services.tradingview_ideas_batch_ingestion.time.sleep", return_value=None)
    def test_sad_inter_ticker_delay_called(self, mock_sleep):
        """[SAD] time.sleep is called between each ticker."""
        self.ingestion.scraper.scrape.return_value = []
        self.ingestion.run()
        assert mock_sleep.call_count == 2   # once per ticker
