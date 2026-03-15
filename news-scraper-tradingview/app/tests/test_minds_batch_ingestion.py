"""
Tests for app/services/tradingview_minds_batch_ingestion.py

Coverage:
  _dedup_key  — uid-based key
  _build_row  — schema structure, timestamp parsing, fallback
  run()       — publishes new items, exchange fallback (NASDAQ→NYSE),
                skips duplicates, empty tickers, exception handling
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import fakeredis
import pytest

from app.services.tradingview_minds_batch_ingestion import TradingViewMindsBatchIngestion


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_mind(
    uid="mind001",
    text="AAPL looking bullish above 200MA.",
    created="2026-03-15 10:00:00",
    author_username="trader123",
    total_likes=25,
    total_comments=5,
    symbols=None,
    url="https://www.tradingview.com/u/trader123/",
):
    return {
        "uid": uid,
        "text": text,
        "created": created,
        "author": {"username": author_username},
        "url": url,
        "total_likes": total_likes,
        "total_comments": total_comments,
        "symbols": symbols or ["NASDAQ:AAPL"],
    }


def _success_response(minds):
    return {"status": "success", "data": minds}


def _failed_response():
    return {"status": "failed", "data": []}


class TestTradingViewMindsBatchIngestion:

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.r = fakeredis.FakeRedis(decode_responses=True)
        self.r.hset("all_identified_tickers", mapping={"AAPL": "1", "JPM": "1"})
        self.ingestion = TradingViewMindsBatchIngestion(self.r)
        self.ingestion.scraper = MagicMock()

    # ── _dedup_key ─────────────────────────────────────────────────────────────

    def test_happy_dedup_key_returns_uid(self):
        """[HAPPY] Dedup key is the mind's uid."""
        mind = _make_mind(uid="abc123")
        assert TradingViewMindsBatchIngestion._dedup_key(mind) == "abc123"

    def test_boundary_dedup_key_empty_uid_returns_empty_string(self):
        """[BOUNDARY] Mind with no uid returns empty string."""
        assert TradingViewMindsBatchIngestion._dedup_key({}) == ""

    # ── _build_row ─────────────────────────────────────────────────────────────

    def test_happy_build_row_schema_structure(self):
        """[HAPPY] Built row has all required top-level keys."""
        row = TradingViewMindsBatchIngestion._build_row(_make_mind(), "AAPL")
        for key in ("id", "content_type", "native_id", "source", "author",
                    "url", "timestamps", "content", "engagement", "metadata"):
            assert key in row, f"Missing key: {key}"

    def test_happy_build_row_content_type_is_mind(self):
        """[HAPPY] content_type is 'mind'."""
        row = TradingViewMindsBatchIngestion._build_row(_make_mind(), "AAPL")
        assert row["content_type"] == "mind"

    def test_happy_build_row_id_prefixed_with_tradingview_minds(self):
        """[HAPPY] id field is prefixed 'tradingview_minds:{uid}'."""
        row = TradingViewMindsBatchIngestion._build_row(_make_mind(uid="xyz"), "AAPL")
        assert row["id"] == "tradingview_minds:xyz"

    def test_happy_build_row_timestamp_parsed_from_string(self):
        """[HAPPY] created string '%Y-%m-%d %H:%M:%S' is converted to ISO."""
        row = TradingViewMindsBatchIngestion._build_row(
            _make_mind(created="2026-03-15 10:00:00"), "AAPL"
        )
        assert "2026-03-15" in row["timestamps"]

    def test_happy_build_row_author_username(self):
        """[HAPPY] author field is populated from mind's author.username."""
        row = TradingViewMindsBatchIngestion._build_row(
            _make_mind(author_username="investorJoe"), "AAPL"
        )
        assert row["author"] == "investorJoe"

    def test_happy_build_row_body_from_text(self):
        """[HAPPY] content.body is populated from mind's text field."""
        row = TradingViewMindsBatchIngestion._build_row(
            _make_mind(text="TSLA breaking resistance!"), "TSLA"
        )
        assert row["content"]["body"] == "TSLA breaking resistance!"
        assert row["content"]["title"] == ""

    def test_happy_build_row_engagement_fields(self):
        """[HAPPY] engagement.score and total_comments are correct."""
        row = TradingViewMindsBatchIngestion._build_row(
            _make_mind(total_likes=10, total_comments=3), "AAPL"
        )
        assert row["engagement"]["score"] == 10
        assert row["engagement"]["total_comments"] == 3
        assert row["engagement"]["upvote_ratio"] is None

    def test_happy_build_row_metadata_ticker(self):
        """[HAPPY] metadata.ticker holds the passed symbol."""
        row = TradingViewMindsBatchIngestion._build_row(_make_mind(), "JPM")
        assert row["metadata"]["ticker"] == "JPM"

    def test_boundary_build_row_invalid_timestamp_falls_back(self):
        """[BOUNDARY] Unparseable created string falls back gracefully."""
        row = TradingViewMindsBatchIngestion._build_row(
            _make_mind(created="not-a-date"), "AAPL"
        )
        assert row["timestamps"] == "not-a-date"

    def test_boundary_build_row_missing_created_falls_back(self):
        """[BOUNDARY] Missing created field produces a valid ISO timestamp."""
        mind = _make_mind()
        del mind["created"]
        row = TradingViewMindsBatchIngestion._build_row(mind, "AAPL")
        assert "T" in row["timestamps"]

    # ── run() ─────────────────────────────────────────────────────────────────

    @patch("app.services.tradingview_minds_batch_ingestion.time.sleep", return_value=None)
    def test_happy_run_publishes_new_minds(self, _sleep):
        """[HAPPY] New minds are published to the Redis stream."""
        minds = [_make_mind(uid=f"uid{i}") for i in range(3)]
        self.ingestion.scraper.get_minds.return_value = _success_response(minds)
        summary = self.ingestion.run()
        assert summary["total_published"] == 6   # 3 minds × 2 tickers
        assert summary["errors"] == []
        assert self.r.xlen("tradingview:minds:raw") == 6

    @patch("app.services.tradingview_minds_batch_ingestion.time.sleep", return_value=None)
    def test_happy_run_skips_duplicates(self, _sleep):
        """[HAPPY] Re-running with the same minds produces duplicates=N, published=0."""
        minds = [_make_mind(uid="uid001")]
        self.ingestion.scraper.get_minds.return_value = _success_response(minds)
        self.ingestion.run()
        summary2 = self.ingestion.run()
        assert summary2["total_published"] == 0
        assert summary2["total_duplicates"] == 2  # 1 × 2 tickers

    @patch("app.services.tradingview_minds_batch_ingestion.time.sleep", return_value=None)
    def test_happy_run_uses_exchange_fallback(self, _sleep):
        """[HAPPY] NASDAQ fails then NYSE succeeds — item is still published."""
        # AAPL: NASDAQ succeeds, JPM: NASDAQ fails, NYSE succeeds
        def scrape(symbol, sort, limit):
            if "NYSE:JPM" in symbol or "NASDAQ:AAPL" in symbol:
                return _success_response([_make_mind(uid=f"uid_{symbol}")])
            return _failed_response()

        self.ingestion.scraper.get_minds.side_effect = scrape
        summary = self.ingestion.run()
        assert summary["total_published"] == 2

    @patch("app.services.tradingview_minds_batch_ingestion.time.sleep", return_value=None)
    def test_happy_run_summary_fields(self, _sleep):
        """[HAPPY] Summary dict contains all expected keys."""
        self.ingestion.scraper.get_minds.return_value = _success_response([])
        summary = self.ingestion.run()
        for key in ("source", "tickers_processed", "total_scraped",
                    "total_published", "total_duplicates", "errors"):
            assert key in summary

    @patch("app.services.tradingview_minds_batch_ingestion.time.sleep", return_value=None)
    def test_boundary_empty_ticker_list(self, _sleep):
        """[BOUNDARY] No tickers → zero counts, no stream entries."""
        self.r.delete("all_identified_tickers")
        summary = self.ingestion.run()
        assert summary["tickers_processed"] == 0
        assert summary["total_published"] == 0

    @patch("app.services.tradingview_minds_batch_ingestion.time.sleep", return_value=None)
    def test_boundary_skips_mind_with_empty_uid(self, _sleep):
        """[BOUNDARY] Mind with missing uid is skipped, not published."""
        minds = [{"uid": "", "text": "test", "created": "2026-01-01 00:00:00",
                  "author": {"username": "x"}, "total_likes": 0, "total_comments": 0}]
        self.ingestion.scraper.get_minds.return_value = _success_response(minds)
        summary = self.ingestion.run()
        assert summary["total_published"] == 0

    @patch("app.services.tradingview_minds_batch_ingestion.time.sleep", return_value=None)
    def test_sad_all_exchanges_fail_no_error_recorded(self, _sleep):
        """[SAD] When all exchange candidates fail, ticker is silently skipped."""
        self.ingestion.scraper.get_minds.return_value = _failed_response()
        summary = self.ingestion.run()
        assert summary["total_published"] == 0
        assert summary["errors"] == []

    @patch("app.services.tradingview_minds_batch_ingestion.time.sleep", return_value=None)
    def test_sad_exception_per_ticker_recorded_and_continues(self, _sleep):
        """[SAD] Exception on one ticker is recorded; other tickers processed."""
        self.ingestion.scraper.get_minds.side_effect = [
            Exception("Network error"),
            _success_response([_make_mind(uid="uid001")]),
            _success_response([_make_mind(uid="uid001")]),
        ]
        summary = self.ingestion.run()
        assert len(summary["errors"]) == 1
        assert summary["total_published"] == 1
