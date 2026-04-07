from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from app.services.tools.general_news import get_general_news
from app.services.tools.trade_history import (
    _get_order_details,
    get_trade_history_details,
)


@pytest.mark.asyncio
async def test_get_general_news_only_query():
    """Test get_general_news with only the query provided."""
    mock_response = {
        "results": [
            {"topic_id": "topic_1", "text_content": "Market News: Stock market update"},
        ]
    }

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = MagicMock(spec=httpx.Response)
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = mock_response
        mock_post.return_value.raise_for_status = MagicMock()

        # Call with only query
        result = await get_general_news.ainvoke({"query": "What is the market doing?"})

        assert "Market News" in result["context"]
        assert "topic_1" in result["context"]
        assert len(result["results"]) == 1
        
        # Verify the payload sent to the mock post
        args, kwargs = mock_post.call_args
        sent_payload = kwargs.get("json", {})
        assert sent_payload["query"] == "What is the market doing?"
        assert sent_payload["tickers"] == []  # Should default to empty list
        assert sent_payload["limit"] == 50


@pytest.mark.asyncio
async def test_get_general_news_date_filtered():
    """Test get_general_news with date filtering using GET /news."""
    mock_response = {
        "results": [
            {"topic_id": "topic_news", "text_content": "Market was bullish today"},
        ]
    }

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = MagicMock(spec=httpx.Response)
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_response
        mock_get.return_value.raise_for_status = MagicMock()

        # Call with start_date and end_date
        result = await get_general_news.ainvoke({
            "query": "how was the market today",
            "start_date": "2026-04-07T00:00:00",
            "end_date": "2026-04-07T23:59:59"
        })

        assert "bullish today" in result["context"]
        
        # Verify the GET request
        args, kwargs = mock_get.call_args
        url = args[0]
        params = kwargs.get("params", {})
        
        assert "/news" in url
        assert params["start_date"] == "2026-04-07T00:00:00"
        assert params["end_date"] == "2026-04-07T23:59:59"


@pytest.mark.asyncio
async def test_get_general_news_success():
    mock_response = {
        "results": [
            {"topic_id": "topic_1", "text_content": "News 1 Content"},
            {"topic_id": "topic_2", "text_content": "News 2 Content"},
        ]
    }

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = MagicMock(spec=httpx.Response)
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = mock_response
        mock_post.return_value.raise_for_status = MagicMock()

        result = await get_general_news.ainvoke({"query": "test", "tickers": ["AAPL"]})

        assert "News 1" in result["context"]
        assert "topic_1" in result["context"]
        assert len(result["results"]) == 2


@pytest.mark.asyncio
async def test_get_general_news_no_results():
    mock_response = {"results": []}

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = MagicMock(spec=httpx.Response)
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = mock_response

        result = await get_general_news.ainvoke({"query": "test", "tickers": ["AAPL"]})

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
