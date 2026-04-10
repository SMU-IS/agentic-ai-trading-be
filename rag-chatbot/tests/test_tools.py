import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.tools.general_news import get_general_news
from app.services.tools.trade_history import (
    _fetch_order_data,
    get_trade_history_details,
)
from app.schemas.order_details import OrderDetailsResponse

@pytest.mark.asyncio
async def test_get_general_news_general_market_uses_get():
    """Test that get_general_news uses GET /news when is_general_market is True."""
    mock_response = [
        {
            "metadata": {
                "headline": "General market news",
                "text_content": "Content",
                "source_domain": "source",
                "timestamp": "2024"
            }
        }
    ]

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = MagicMock(spec=httpx.Response)
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_response
        mock_get.return_value.raise_for_status = MagicMock()

        result = await get_general_news.ainvoke({
            "query": "market",
            "is_general_market": True
        })

        assert "General market news" in result["context"]
        assert len(result["results"]) == 1

@pytest.mark.asyncio
async def test_fetch_order_data_success():
    mock_response = {
        "symbol": "AAPL",
        "filled_avg_price": 150.0,
        "side": "buy",
        "trading_agent_reasonings": "RSI oversold"
    }

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = MagicMock(spec=httpx.Response)
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_response
        mock_get.return_value.raise_for_status = MagicMock()

        result = await _fetch_order_data("order123", "user123")

        assert result["symbol"] == "AAPL"
        assert result["filled_avg_price"] == 150.0

@pytest.mark.asyncio
async def test_get_trade_history_details_success():
    mock_raw_data = {
        "symbol": "AAPL",
        "filled_avg_price": 150.0,
        "side": "buy",
        "trading_agent_reasonings": "RSI oversold"
    }

    with patch(
        "app.services.tools.trade_history._fetch_order_data", new_callable=AsyncMock
    ) as mock_fetch:
        mock_fetch.return_value = mock_raw_data

        config = {"metadata": {"user_id": "user123"}}
        result = await get_trade_history_details.ainvoke(
            {"order_id": "order123"}, config=config
        )

        assert isinstance(result, OrderDetailsResponse)
        assert result.ticker == "AAPL"
        assert result.entry_price == 150.0
        assert result.reasoning == "RSI oversold"

@pytest.mark.asyncio
async def test_get_trade_history_details_failure():
    with patch(
        "app.services.tools.trade_history._fetch_order_data",
        side_effect=Exception("API Error"),
    ):
        with pytest.raises(Exception) as excinfo:
            config = {"metadata": {"user_id": "user123"}}
            await get_trade_history_details.ainvoke(
                {"order_id": "order123"}, config=config
            )
        assert "Unable to retrieve trade history" in str(excinfo.value)
