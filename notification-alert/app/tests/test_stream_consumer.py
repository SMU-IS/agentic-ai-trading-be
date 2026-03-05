import json
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    return asyncio.run(coro)


class TestStreamConsumer:

    @pytest.fixture(autouse=True)
    def _setup(self):
        with patch("app.workers.stream_consumer.Redis"):
            from app.workers.stream_consumer import StreamConsumer
            from app.core.config import env_config
            self.svc = StreamConsumer()
            self.mock_r = AsyncMock()
            self.svc.r = self.mock_r
            self.news = env_config.redis_notification_stream
            self.analysis = env_config.redis_analysis_stream
            self.trade = env_config.redis_trade_stream
            self.svc.streams = {
                self.news: "news_notification_group",
                self.analysis: "analysis_notification_group",
                self.trade: "trade_notification_group",
            }

    # HAPPY PATH ---------------------------------------------------------------

    def test_happy_create_groups_creates_all_three(self):
        """[HAPPY] create_groups() calls xgroup_create for each of the 3 streams."""
        self.mock_r.xgroup_create = AsyncMock()
        _run(self.svc.create_groups())
        assert self.mock_r.xgroup_create.await_count == 3

    def test_happy_news_event_calls_notify_users(self):
        """[HAPPY] News event triggers notify_users with correct type and id."""
        self.mock_r.xgroup_create = AsyncMock(side_effect=Exception("BUSYGROUP"))
        news_data = {"id": "reddit:n1", "headline": "Apple beats",
                     "tickers": json.dumps([{"symbol": "AAPL"}]),
                     "event_description": "Strong Q4"}

        called = [0]
        async def _xreadgroup(groupname, consumername, streams, count, block):
            called[0] += 1
            stream = list(streams.keys())[0]
            if stream == self.news and called[0] <= 3:
                return [(stream, [("1-0", news_data)])]
            raise asyncio.CancelledError()

        self.mock_r.xreadgroup = _xreadgroup
        self.mock_r.xack = AsyncMock()

        with patch("app.workers.stream_consumer.notify_users",
                   new=AsyncMock(return_value=True)) as mock_notify:
            with pytest.raises(asyncio.CancelledError):
                _run(self.svc.async_start())

        payload = mock_notify.call_args[0][0]
        assert payload["type"] == "NEWS_RECEIVED"
        assert payload["news_id"] == "reddit:n1"

    def test_happy_signal_event_fetches_api_and_notifies(self):
        """[HAPPY] Analysis event fetches signal via HTTP and calls notify_users."""
        self.mock_r.xgroup_create = AsyncMock(side_effect=Exception("BUSYGROUP"))
        self.mock_r.xpending_range = AsyncMock(return_value=[])
        call_counts = {}

        async def _xreadgroup(groupname, consumername, streams, count, block):
            stream = list(streams.keys())[0]
            call_counts[stream] = call_counts.get(stream, 0) + 1
            if stream == self.analysis and call_counts[stream] <= 2:
                return [(stream, [("3-0", {"signal_id": "sig_001"})])]
            if stream == self.analysis:
                raise asyncio.CancelledError()
            return []

        self.mock_r.xreadgroup = _xreadgroup
        self.mock_r.xack = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"signal_id": "sig_001", "ticker": "AAPL"}
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("app.workers.stream_consumer.notify_users",
                   new=AsyncMock(return_value=True)) as mock_notify, \
             patch("app.workers.stream_consumer.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            with pytest.raises(asyncio.CancelledError):
                _run(self.svc.async_start())
            assert mock_notify.called
            assert mock_notify.call_args[0][0]["type"] == "SIGNAL_GENERATED"

    def test_happy_trade_event_fetches_api_and_notifies(self):
        """[HAPPY] Trade event fetches order via HTTP and notifies with correct payload."""
        self.mock_r.xgroup_create = AsyncMock(side_effect=Exception("BUSYGROUP"))
        self.mock_r.xpending_range = AsyncMock(return_value=[])
        call_counts = {}

        async def _xreadgroup(groupname, consumername, streams, count, block):
            stream = list(streams.keys())[0]
            call_counts[stream] = call_counts.get(stream, 0) + 1
            if stream == self.trade and call_counts[stream] <= 2:
                return [(stream, [("4-0", {"order_id": "ord_999"})])]
            if stream == self.trade:
                raise asyncio.CancelledError()
            return []

        self.mock_r.xreadgroup = _xreadgroup
        self.mock_r.xack = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"order_id": "ord_999", "status": "FILLED"}
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("app.workers.stream_consumer.notify_users",
                   new=AsyncMock(return_value=True)) as mock_notify, \
             patch("app.workers.stream_consumer.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            with pytest.raises(asyncio.CancelledError):
                _run(self.svc.async_start())
            assert mock_notify.called
            payload = mock_notify.call_args[0][0]
            assert payload["type"] == "TRADE_PLACED"
            assert payload["order"]["order_id"] == "ord_999"

    # BOUNDARY PATH ------------------------------------------------------------

    def test_boundary_empty_xreadgroup_checks_pending(self):
        """[BOUNDARY] Empty xreadgroup → xpending_range consulted for stale messages."""
        self.mock_r.xgroup_create = AsyncMock(side_effect=Exception("BUSYGROUP"))
        called = [0]

        async def _xreadgroup(groupname, consumername, streams, count, block):
            called[0] += 1
            if called[0] > 3:
                raise asyncio.CancelledError()
            return []

        self.mock_r.xreadgroup = _xreadgroup
        self.mock_r.xpending_range = AsyncMock(return_value=[{"message_id": "5-0"}])
        self.mock_r.xclaim = AsyncMock(return_value=[])

        with patch("app.workers.stream_consumer.notify_users",
                   new=AsyncMock(return_value=False)):
            with pytest.raises(asyncio.CancelledError):
                _run(self.svc.async_start())

        self.mock_r.xpending_range.assert_awaited()

    def test_boundary_news_not_acked_when_not_delivered(self):
        """[BOUNDARY] xack is NOT called when notify_users returns False."""
        self.mock_r.xgroup_create = AsyncMock(side_effect=Exception("BUSYGROUP"))
        news_data = {"id": "reddit:n2", "headline": "Test",
                     "tickers": "[]", "event_description": ""}

        called = [0]
        async def _xreadgroup(groupname, consumername, streams, count, block):
            called[0] += 1
            stream = list(streams.keys())[0]
            if stream == self.news and called[0] <= 3:
                return [(stream, [("2-0", news_data)])]
            raise asyncio.CancelledError()

        self.mock_r.xreadgroup = _xreadgroup
        self.mock_r.xack = AsyncMock()

        with patch("app.workers.stream_consumer.notify_users",
                   new=AsyncMock(return_value=False)):
            with pytest.raises(asyncio.CancelledError):
                _run(self.svc.async_start())

        self.mock_r.xack.assert_not_awaited()

    # SAD PATH -----------------------------------------------------------------

    def test_sad_create_groups_busygroup_ignored(self):
        """[SAD] BUSYGROUP on create_groups is silently ignored."""
        self.mock_r.xgroup_create = AsyncMock(
            side_effect=Exception("BUSYGROUP already exists"))
        _run(self.svc.create_groups())

    def test_sad_create_groups_unexpected_error_raises(self):
        """[SAD] Non-BUSYGROUP exception from xgroup_create is re-raised."""
        self.mock_r.xgroup_create = AsyncMock(side_effect=Exception("WRONGTYPE"))
        with pytest.raises(Exception, match="WRONGTYPE"):
            _run(self.svc.create_groups())

    def test_sad_cancelled_error_propagates(self):
        """[SAD] asyncio.CancelledError from xreadgroup bubbles up correctly."""
        self.mock_r.xgroup_create = AsyncMock(side_effect=Exception("BUSYGROUP"))
        self.mock_r.xreadgroup = AsyncMock(side_effect=asyncio.CancelledError())

        with pytest.raises(asyncio.CancelledError):
            _run(self.svc.async_start())

    def test_sad_general_exception_sleeps_and_retries(self):
        """[SAD] Generic exception triggers sleep and retry; not a hard crash."""
        self.mock_r.xgroup_create = AsyncMock(side_effect=Exception("BUSYGROUP"))
        called = [0]

        async def _xreadgroup(groupname, consumername, streams, count, block):
            called[0] += 1
            if called[0] == 1:
                raise Exception("connection reset")
            raise asyncio.CancelledError()

        self.mock_r.xreadgroup = _xreadgroup

        with patch("asyncio.sleep", new=AsyncMock()):
            with pytest.raises(asyncio.CancelledError):
                _run(self.svc.async_start())

        assert called[0] == 2
