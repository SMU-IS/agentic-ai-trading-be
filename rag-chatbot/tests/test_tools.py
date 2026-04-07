from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from app.services.tools.general_news import get_general_news
from app.services.tools.trade_history import (
    _get_order_details,
    get_trade_history_details,
)


@pytest.mark.asyncio
async def test_get_general_news_general_market_uses_get():
    """Test that get_general_news uses GET /news when is_general_market is True."""
    mock_response = {
        "results": [
            {"topic_id": "topic_news", "text_content": "General market news"},
        ]
    }

    with patch("app.services.tools.general_news.httpx.AsyncClient") as mock_client_class:
        mock_client = mock_client_class.return_value.__aenter__.return_value
        mock_client.get = AsyncMock()
        mock_client.get.return_value = MagicMock(spec=httpx.Response)
        mock_client.get.return_value.status_code = 200
        mock_client.get.return_value.json.return_value = mock_response
        mock_client.get.return_value.raise_for_status = MagicMock()

        # Call with is_general_market=True
        result = await get_general_news.ainvoke({
            "query": "how is the market today",
            "is_general_market": True,
            "start_date": "2026-04-07T00:00:00",
            "end_date": "2026-04-07T23:59:59"
        })

        assert "General market" in result["context"]
        
        # Verify the GET request was made
        args, kwargs = mock_client.get.call_args
        url = args[0]
        params = kwargs.get("params", {})
        assert "/news" in url
        assert params["start_date"] == "2026-04-07T00:00:00"


@pytest.mark.asyncio
async def test_get_general_news_specific_topic_uses_post():
    """Test that get_general_news uses POST /query when is_general_market is False."""
    mock_response = {
        "results": [
            {"topic_id": "topic_google", "text_content": "Google news"},
        ]
    }

    with patch("app.services.tools.general_news.httpx.AsyncClient") as mock_client_class:
        mock_client = mock_client_class.return_value.__aenter__.return_value
        mock_client.post = AsyncMock()
        mock_client.post.return_value = MagicMock(spec=httpx.Response)
        mock_client.post.return_value.status_code = 200
        mock_client.post.return_value.json.return_value = mock_response
        mock_client.post.return_value.raise_for_status = MagicMock()

        # Call with is_general_market=False
        result = await get_general_news.ainvoke({
            "query": "Tell me about Google",
            "is_general_market": False,
            "tickers": [],
            "start_date": "2026-04-01T00:00:00",
            "end_date": "2026-04-07T23:59:59"
        })

        assert "Google news" in result["context"]
        
        # Verify the POST request was made
        args, kwargs = mock_client.post.call_args
        payload = kwargs.get("json", {})
        assert payload["query"] == "Tell me about Google"
        assert "/query" in args[0]


@pytest.mark.asyncio
async def test_get_general_news_with_ticker_uses_post():
    """Test that get_general_news uses POST /query when tickers are provided."""
    mock_response = {
        "results": [
            {"topic_id": "topic_aapl", "text_content": "AAPL news"},
        ]
    }

    with patch("app.services.tools.general_news.httpx.AsyncClient") as mock_client_class:
        mock_client = mock_client_class.return_value.__aenter__.return_value
        mock_client.post = AsyncMock()
        mock_client.post.return_value = MagicMock(spec=httpx.Response)
        mock_client.post.return_value.status_code = 200
        mock_client.post.return_value.json.return_value = mock_response
        mock_client.post.return_value.raise_for_status = MagicMock()

        # Call with tickers (is_general_market defaults to False)
        result = await get_general_news.ainvoke({
            "query": "AAPL news",
            "tickers": ["AAPL"],
            "start_date": "2026-04-01T00:00:00"
        })

        assert "AAPL news" in result["context"]
        
        # Verify the POST request was made
        args, kwargs = mock_client.post.call_args
        payload = kwargs.get("json", {})
        assert payload["tickers"] == ["AAPL"]
        assert "/query" in args[0]


@pytest.mark.asyncio
async def test_get_general_news_with_none_tickers():
    """Test that get_general_news handles tickers=None by defaulting to []."""
    mock_response = {"results": []}

    with patch("app.services.tools.general_news.httpx.AsyncClient") as mock_client_class:
        mock_client = mock_client_class.return_value.__aenter__.return_value
        mock_client.post = AsyncMock()
        mock_client.post.return_value = MagicMock(spec=httpx.Response)
        mock_client.post.return_value.status_code = 200
        mock_client.post.return_value.json.return_value = mock_response
        mock_client.post.return_value.raise_for_status = MagicMock()

        # Explicitly pass None for tickers - now allowed by schema
        await get_general_news.ainvoke({
            "query": "some news",
            "tickers": None,
            "is_general_market": False
        })
        
        # Verify it used POST /query (default for is_general_market=False)
        args, kwargs = mock_client.post.call_args
        assert "/query" in args[0]


@pytest.mark.asyncio
async def test_get_general_news_no_results():
    mock_response = {"results": []}

    with patch("app.services.tools.general_news.httpx.AsyncClient") as mock_client_class:
        mock_client = mock_client_class.return_value.__aenter__.return_value
        mock_client.post = AsyncMock()
        mock_client.post.return_value = MagicMock(spec=httpx.Response)
        mock_client.post.return_value.status_code = 200
        mock_client.post.return_value.json.return_value = mock_response
        mock_client.post.return_value.raise_for_status = MagicMock()

        result = await get_general_news.ainvoke({"query": "test", "tickers": [], "is_general_market": False})

        assert "No relevant news found" in result["context"]
        assert result["results"] == []


@pytest.mark.asyncio
async def test_get_order_details_success():
    mock_response = {
        "symbol": "AAPL",
        "filled_avg_price": 150.0,
        "side": "buy",
        "risk_evaluation": "low",
        "risk_adjustments_made": "none",
        "trading_agent_reasonings": "RSI oversold",
    }

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = MagicMock(spec=httpx.Response)
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_response
        mock_get.return_value.raise_for_status = MagicMock()

        result = await _get_order_details("order123", "user123")

        assert result == ("AAPL", 150.0, "buy", "low", "none", "RSI oversold")


@pytest.mark.asyncio
async def test_get_trade_history_details_success():
    mock_order_details = ("AAPL", 150.0, "buy", "low", "none", "RSI oversold")

    with patch(
        "app.services.tools.trade_history._get_order_details", new_callable=AsyncMock
    ) as mock_get_details:
        mock_get_details.return_value = mock_order_details

        config = {"metadata": {"user_id": "user123"}}
        result = await get_trade_history_details.ainvoke(
            {"order_id": "order123"}, config=config
        )

        assert result.ticker == "AAPL"
        assert result.entry_price == 150.0
        assert result.action == "buy"
        assert result.reasoning == "RSI oversold"


@pytest.mark.asyncio
async def test_get_trade_history_details_failure():
    with patch(
        "app.services.tools.trade_history._get_order_details",
        side_effect=Exception("API Error"),
    ):
        with pytest.raises(Exception) as excinfo:
            config = {"metadata": {"user_id": "user123"}}
            await get_trade_history_details.ainvoke(
                {"order_id": "order123"}, config=config
            )

        assert "Unable to retrieve trade history details" in str(excinfo.value)
