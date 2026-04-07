from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from app.services.tools.general_news import get_general_news
from app.services.tools.trade_history import (
    _get_order_details,
    get_trade_history_details,
)


@pytest.mark.asyncio
async def test_get_general_news_no_ticker_uses_get():
    """Test that get_general_news uses GET /news when no tickers are provided."""
    mock_response = {
        "results": [
            {"topic_id": "topic_news", "text_content": "General market news"},
        ]
    }

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = MagicMock(spec=httpx.Response)
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_response
        mock_get.return_value.raise_for_status = MagicMock()

        # Call with no tickers
        result = await get_general_news.ainvoke({
            "query": "how is the market today",
            "tickers": [],
            "start_date": "2026-04-07T00:00:00",
            "end_date": "2026-04-07T23:59:59"
        })

        assert "General market" in result["context"]
        
        # Verify the GET request was made
        args, kwargs = mock_get.call_args
        url = args[0]
        params = kwargs.get("params", {})
        assert "/news" in url
        assert params["start_date"] == "2026-04-07T00:00:00"


@pytest.mark.asyncio
async def test_get_general_news_with_ticker_uses_post():
    """Test that get_general_news uses POST /query when tickers are provided."""
    mock_response = {
        "results": [
            {"topic_id": "topic_aapl", "text_content": "AAPL news"},
        ]
    }

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = MagicMock(spec=httpx.Response)
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = mock_response
        mock_post.return_value.raise_for_status = MagicMock()

        # Call with tickers
        result = await get_general_news.ainvoke({
            "query": "Tell me any news about Apple",
            "tickers": ["AAPL"],
            "start_date": "2026-04-01T00:00:00",
            "end_date": "2026-04-07T23:59:59"
        })

        assert "AAPL news" in result["context"]
        
        # Verify the POST request was made
        args, kwargs = mock_post.call_args
        payload = kwargs.get("json", {})
        assert payload["tickers"] == ["AAPL"]
        assert payload["start_date"] == "2026-04-01T00:00:00"


@pytest.mark.asyncio
async def test_get_general_news_with_missing_tickers():
    """Test that get_general_news handles missing tickers by defaulting to []."""
    mock_response = {"results": []}

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = MagicMock(spec=httpx.Response)
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_response
        mock_get.return_value.raise_for_status = MagicMock()

        # Omit tickers from input
        await get_general_news.ainvoke({
            "query": "market news",
            "start_date": "2026-04-07T00:00:00"
        })
        
        # Should not raise error and should have used GET /news
        args, kwargs = mock_get.call_args
        assert "/news" in args[0]


@pytest.mark.asyncio
async def test_get_general_news_only_query():
    """Test get_general_news with only the query provided (no tickers, no date)."""
    mock_response = {
        "results": [
            {"topic_id": "topic_1", "text_content": "Market News: Stock market update"},
        ]
    }

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = MagicMock(spec=httpx.Response)
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_response
        mock_get.return_value.raise_for_status = MagicMock()

        # No tickers, no date -> defaults to GET /news in the current logic if we pass start_date in node
        # But here we test the tool directly. Tool says: if not tickers -> GET /news
        result = await get_general_news.ainvoke({"query": "What is the market doing?"})

        assert "Market News" in result["context"]


@pytest.mark.asyncio
async def test_get_general_news_no_results():
    mock_response = {"results": []}

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = MagicMock(spec=httpx.Response)
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_response

        result = await get_general_news.ainvoke({"query": "test", "tickers": []})

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
