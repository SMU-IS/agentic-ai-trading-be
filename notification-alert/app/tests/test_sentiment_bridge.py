import json
import asyncio
import pytest
from unittest.mock import AsyncMock, patch


def _run(coro):
    return asyncio.run(coro)


class TestSentimentBridge:

    @pytest.fixture(autouse=True)
    def _setup(self):
        with patch("app.workers.sentiment_to_notification.Redis"):
            from app.workers.sentiment_to_notification import SentimentBridge
            self.svc = SentimentBridge()
            self.mock_r = AsyncMock()
            self.svc.r = self.mock_r
            self.svc.sentiment_stream = "sentiment_stream"
            self.svc.notification_stream = "notification_stream"

    # HAPPY PATH ---------------------------------------------------------------

    def test_happy_event_written_to_notification_stream(self):
        """[HAPPY] Valid event is transformed and written to notification stream."""
        ticker_meta = {"NVDA": {"event_type": "EARNINGS", "sentiment_label": "POSITIVE",
                                "event_description": "Beat estimates"}}
        data = {"ticker_metadata": json.dumps(ticker_meta),
                "id": '"reddit:n1"',
                "content": json.dumps({"title": "Nvidia blows past estimates"})}

        self.mock_r.xread = AsyncMock(side_effect=[
            [("sentiment_stream", [("1-0", data)])],
            asyncio.CancelledError()
        ])
        self.mock_r.xadd = AsyncMock()

        with pytest.raises(asyncio.CancelledError):
            _run(self.svc.async_start())

        added = self.mock_r.xadd.call_args[0][1]
        assert added["id"] == "reddit:n1"
        assert added["headline"] == "Nvidia blows past estimates"
        assert json.loads(added["tickers"])[0]["symbol"] == "NVDA"

    def test_happy_multiple_tickers_all_in_output(self):
        """[HAPPY] All tickers from an event appear in the tickers list."""
        ticker_meta = {
            "AAPL": {"event_type": "NEWS", "sentiment_label": "NEUTRAL", "event_description": ""},
            "MSFT": {"event_type": "NEWS", "sentiment_label": "POSITIVE", "event_description": ""},
        }
        data = {"ticker_metadata": json.dumps(ticker_meta),
                "id": '"reddit:m1"',
                "content": json.dumps({"title": "Big tech news"})}

        self.mock_r.xread = AsyncMock(side_effect=[
            [("sentiment_stream", [("2-0", data)])],
            asyncio.CancelledError()
        ])
        self.mock_r.xadd = AsyncMock()

        with pytest.raises(asyncio.CancelledError):
            _run(self.svc.async_start())

        tickers = json.loads(self.mock_r.xadd.call_args[0][1]["tickers"])
        assert {t["symbol"] for t in tickers} == {"AAPL", "MSFT"}

    def test_happy_event_descriptions_joined(self):
        """[HAPPY] event_description from multiple tickers are all present."""
        ticker_meta = {
            "X": {"event_type": "NEWS", "sentiment_label": "NEGATIVE", "event_description": "Desc A"},
            "Y": {"event_type": "NEWS", "sentiment_label": "POSITIVE", "event_description": "Desc B"},
        }
        data = {"ticker_metadata": json.dumps(ticker_meta),
                "id": '"reddit:d1"',
                "content": json.dumps({"title": "Market update"})}

        self.mock_r.xread = AsyncMock(side_effect=[
            [("sentiment_stream", [("3-0", data)])],
            asyncio.CancelledError()
        ])
        self.mock_r.xadd = AsyncMock()

        with pytest.raises(asyncio.CancelledError):
            _run(self.svc.async_start())

        desc = self.mock_r.xadd.call_args[0][1]["event_description"]
        assert "Desc A" in desc and "Desc B" in desc

    # BOUNDARY PATH ------------------------------------------------------------

    def test_boundary_empty_xread_does_not_write(self):
        """[BOUNDARY] Empty xread result loops without calling xadd."""
        self.mock_r.xread = AsyncMock(side_effect=[[], [], asyncio.CancelledError()])
        self.mock_r.xadd = AsyncMock()

        with pytest.raises(asyncio.CancelledError):
            _run(self.svc.async_start())

        self.mock_r.xadd.assert_not_awaited()

    # SAD PATH -----------------------------------------------------------------

    def test_sad_malformed_ticker_metadata_propagates(self):
        """[SAD] Bad JSON in ticker_metadata crashes the loop — no per-event guard."""
        data = {"ticker_metadata": "not-json",
                "id": '"reddit:bad"',
                "content": json.dumps({"title": "Some title"})}

        self.mock_r.xread = AsyncMock(return_value=[
            ("sentiment_stream", [("1-0", data)])
        ])
        self.mock_r.xadd = AsyncMock()

        with pytest.raises(json.JSONDecodeError):
            _run(self.svc.async_start())


    def test_sad_missing_ticker_metadata_propagates(self):
        """[SAD] None ticker_metadata crashes on .strip() — no guard."""
        data = {"id": '"reddit:nometa"',
                "content": json.dumps({"title": "Something"})}
        # no ticker_metadata key at all

        self.mock_r.xread = AsyncMock(return_value=[
            ("sentiment_stream", [("2-0", data)])
        ])
        self.mock_r.xadd = AsyncMock()

        with pytest.raises((AttributeError, TypeError)):
            _run(self.svc.async_start())


    def test_sad_xread_exception_sleeps_and_retries(self):
        """[SAD] xread failure → sleep(5) + retry; CancelledError on second call exits."""
        self.mock_r.xread = AsyncMock(side_effect=[
            Exception("connection reset"),
            asyncio.CancelledError()
        ])
        self.mock_r.xadd = AsyncMock()

        with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
            with pytest.raises(asyncio.CancelledError):
                _run(self.svc.async_start())

        mock_sleep.assert_awaited_once_with(5)
        self.mock_r.xadd.assert_not_awaited()
