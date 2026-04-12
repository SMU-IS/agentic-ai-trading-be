import json
import asyncio
import pytest
from unittest.mock import AsyncMock, patch


def _run(coro):
    return asyncio.run(coro)


class TestSentimentAggregator:

    @pytest.fixture(autouse=True)
    def _setup(self):
        with patch("app.workers.sentiment_to_aggregator.Redis"):
            from app.workers.sentiment_to_aggregator import SentimentAggregator
            self.svc = SentimentAggregator()
            self.mock_r = AsyncMock()
            self.svc.r = self.mock_r
            self.svc.sentiment_stream = "sentiment_stream"
            self.svc.aggregator_stream = "aggregator_stream"
            self.svc.group_name = "test_group"
            self.svc.consumer_name = "test_consumer"

    # HAPPY PATH ---------------------------------------------------------------

    def test_happy_create_group(self):
        """[HAPPY] Group created successfully; xgroup_create called once."""
        self.mock_r.xgroup_create = AsyncMock()
        _run(self.svc.create_group())
        self.mock_r.xgroup_create.assert_awaited_once()

    def test_happy_event_written_and_acked(self):
        """[HAPPY] Valid event → xadd to aggregator stream + xack."""
        ticker_meta = {"AAPL": {"event_type": "EARNINGS", "sentiment_score": 0.8,
                                "event_description": "Beat", "sentiment_reasoning": "Strong Q4"}}
        event_id = "1700000000000-0"
        data = {"ticker_metadata": json.dumps(ticker_meta),
                "id": '"reddit:abc"', "content": json.dumps({"title": "Apple beats"})}

        self.mock_r.xgroup_create = AsyncMock(side_effect=Exception("BUSYGROUP"))
        self.mock_r.xreadgroup = AsyncMock(side_effect=[
            [("sentiment_stream", [(event_id, data)])],
            asyncio.CancelledError()
        ])
        self.mock_r.hset = AsyncMock()
        self.mock_r.xadd = AsyncMock()
        self.mock_r.xack = AsyncMock()

        with pytest.raises(asyncio.CancelledError):
            _run(self.svc.async_start())

        self.mock_r.xack.assert_awaited_with("sentiment_stream", "test_group", event_id)
        added = self.mock_r.xadd.call_args[0][1]
        assert added["ticker"] == "AAPL"
        assert added["event_type"] == "NEWS_UPDATE"

    def test_happy_vectorised_timestamp_written(self):
        """[HAPPY] vectorised_timestamp is set in Redis after processing."""
        ticker_meta = {"TSLA": {"event_type": "NEWS", "sentiment_score": 0.5,
                                "event_description": "", "sentiment_reasoning": ""}}
        data = {"ticker_metadata": json.dumps(ticker_meta), "id": '"reddit:xyz"'}

        self.mock_r.xgroup_create = AsyncMock(side_effect=Exception("BUSYGROUP"))
        self.mock_r.xreadgroup = AsyncMock(side_effect=[
            [("sentiment_stream", [("1700000000000-0", data)])],
            asyncio.CancelledError()
        ])
        self.mock_r.hset = AsyncMock()
        self.mock_r.xadd = AsyncMock()
        self.mock_r.xack = AsyncMock()

        with pytest.raises(asyncio.CancelledError):
            _run(self.svc.async_start())

        hset_call = self.mock_r.hset.call_args
        assert "reddit:xyz" in hset_call[0][0]
        assert hset_call[0][1] == "aggregator_timestamp"

    # BOUNDARY PATH ------------------------------------------------------------

    def test_boundary_empty_xreadgroup_triggers_pending_check(self):
        """[BOUNDARY] Empty xreadgroup result → xpending_range is consulted."""
        self.mock_r.xgroup_create = AsyncMock(side_effect=Exception("BUSYGROUP"))
        self.mock_r.xreadgroup = AsyncMock(side_effect=[[], asyncio.CancelledError()])
        self.mock_r.xpending_range = AsyncMock(return_value=[])

        with pytest.raises(asyncio.CancelledError):
            _run(self.svc.async_start())

        self.mock_r.xpending_range.assert_awaited()

    # SAD PATH -----------------------------------------------------------------

    def test_sad_create_group_busygroup_ignored(self):
        """[SAD] BUSYGROUP exception on create_group is silently swallowed."""
        self.mock_r.xgroup_create = AsyncMock(
            side_effect=Exception("BUSYGROUP Consumer Group name already exists")
        )
        _run(self.svc.create_group())  # must not raise

    def test_sad_create_group_other_error_propagates(self):
        """[SAD] Non-BUSYGROUP exception from xgroup_create is re-raised."""
        self.mock_r.xgroup_create = AsyncMock(side_effect=Exception("WRONGTYPE"))
        with pytest.raises(Exception, match="WRONGTYPE"):
            _run(self.svc.create_group())

    def test_happy_source_set_when_subreddit_present(self):
        """[HAPPY] subreddit in metadata → source field is prefixed with 'reddit:'."""
        ticker_meta = {"AAPL": {"event_type": "NEWS", "sentiment_score": 0.5,
                                "event_description": "", "sentiment_reasoning": ""}}
        data = {
            "ticker_metadata": json.dumps(ticker_meta),
            "id": '"reddit:sub1"',
            "metadata": json.dumps({"subreddit": "investing"}),
        }
        self.mock_r.xgroup_create = AsyncMock(side_effect=Exception("BUSYGROUP"))
        self.mock_r.xreadgroup = AsyncMock(side_effect=[
            [("sentiment_stream", [("1700000000000-0", data)])],
            asyncio.CancelledError(),
        ])
        self.mock_r.hset = AsyncMock()
        self.mock_r.xadd = AsyncMock()
        self.mock_r.xack = AsyncMock()

        with pytest.raises(asyncio.CancelledError):
            _run(self.svc.async_start())

        added = self.mock_r.xadd.call_args[0][1]
        assert added["source"] == "reddit:investing"

    def test_boundary_xclaim_results_are_processed(self):
        """[BOUNDARY] When xclaim returns claimed messages, they are fully processed."""
        ticker_meta = {"GOOG": {"event_type": "NEWS", "sentiment_score": 0.7,
                                "event_description": "", "sentiment_reasoning": ""}}
        claimed_data = [("1700000000001-0", {"ticker_metadata": json.dumps(ticker_meta),
                                              "id": '"reddit:claim1"'})]

        call_num = [0]

        async def _xreadgroup(*args, **kwargs):
            call_num[0] += 1
            if call_num[0] == 1:
                return []
            raise asyncio.CancelledError()

        self.mock_r.xgroup_create = AsyncMock(side_effect=Exception("BUSYGROUP"))
        self.mock_r.xreadgroup = _xreadgroup
        self.mock_r.xpending_range = AsyncMock(
            return_value=[{"message_id": "1700000000001-0"}]
        )
        self.mock_r.xclaim = AsyncMock(return_value=claimed_data)
        self.mock_r.hset = AsyncMock()
        self.mock_r.xadd = AsyncMock()
        self.mock_r.xack = AsyncMock()

        with pytest.raises(asyncio.CancelledError):
            _run(self.svc.async_start())

        self.mock_r.xadd.assert_awaited()
        self.mock_r.xack.assert_awaited()

    def test_boundary_xclaim_empty_result_continues_loop(self):
        """[BOUNDARY] xclaim returning [] leaves messages empty; loop continues without processing."""
        call_num = [0]

        async def _xreadgroup(*args, **kwargs):
            call_num[0] += 1
            if call_num[0] == 1:
                return []
            raise asyncio.CancelledError()

        self.mock_r.xgroup_create = AsyncMock(side_effect=Exception("BUSYGROUP"))
        self.mock_r.xreadgroup = _xreadgroup
        self.mock_r.xpending_range = AsyncMock(return_value=[{"message_id": "1-0"}])
        self.mock_r.xclaim = AsyncMock(return_value=[])  # empty → else: messages = []
        self.mock_r.xadd = AsyncMock()

        with pytest.raises(asyncio.CancelledError):
            _run(self.svc.async_start())

        self.mock_r.xadd.assert_not_awaited()

    def test_sad_malformed_ticker_metadata_does_not_crash(self):
        """[SAD] Bad JSON in ticker_metadata is caught; loop continues."""
        data = {"ticker_metadata": "not-json"}
        self.mock_r.xgroup_create = AsyncMock(side_effect=Exception("BUSYGROUP"))
        self.mock_r.xreadgroup = AsyncMock(side_effect=[
            [("sentiment_stream", [("1-0", data)])],
            asyncio.CancelledError()
        ])
        self.mock_r.xpending_range = AsyncMock(return_value=[])

        with pytest.raises(asyncio.CancelledError):
            _run(self.svc.async_start())  # must not raise JSONDecodeError
