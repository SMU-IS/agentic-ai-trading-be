from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from app.services.tools.general_news import get_general_news
from app.services.tools.trade_history import (
    _get_order_details,
    get_trade_history_details,
)


@pytest.mark.asyncio
async def test_get_general_news_success():
    mock_response = {
        "results": [
            {"headline": "News 1", "content_preview": "Content 1"},
            {"headline": "News 2", "content_preview": "Content 2"},
        ]
    }

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = MagicMock(spec=httpx.Response)
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = mock_response
        mock_post.return_value.raise_for_status = MagicMock()

        result = await get_general_news.ainvoke({"query": "test", "tickers": ["AAPL"]})

        assert "News 1" in result["context"]
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

        result = await _get_order_details("order123")

        assert result == ("AAPL", 150.0, "buy", "low", "none", "RSI oversold")


@pytest.mark.asyncio
async def test_get_trade_history_details_success():
    mock_order_details = ("AAPL", 150.0, "buy", "low", "none", "RSI oversold")

    with patch(
        "app.services.tools.trade_history._get_order_details", new_callable=AsyncMock
    ) as mock_get_details:
        mock_get_details.return_value = mock_order_details

        result = await get_trade_history_details.ainvoke(
            {"query": "why buy?", "order_id": "order123"}
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
            await get_trade_history_details.ainvoke(
                {"query": "why buy?", "order_id": "order123"}
            )

        assert "Unable to retrieve trade history details" in str(excinfo.value)
