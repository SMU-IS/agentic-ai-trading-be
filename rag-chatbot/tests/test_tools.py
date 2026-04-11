from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.schemas.order_details import OrderDetailsResponse
from app.services.tools.general_news import _fetch_news_from_api, get_general_news
from app.services.tools.trade_history import (
    _fetch_order_data,
    get_trade_history_details,
)
from app.services.tools.trade_history_list import (
    _fetch_raw_trade_history,
    _transform_to_order_summaries,
    get_trade_history_list,
)


@pytest.mark.asyncio
async def test_get_general_news_general_market_uses_get():
    """Test that get_general_news uses GET /news when is_general_market is True."""
    mock_response = [
        {
            "metadata": {
                "headline": "General market news",
                "text_content": "Content",
                "source_domain": "source",
                "timestamp": "2024",
            }
        }
    ]

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json = MagicMock(return_value=mock_response)
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp

        result = await get_general_news.ainvoke(
            {"query": "market", "is_general_market": True}
        )

        assert "General market news" in result["context"]
        assert len(result["results"]) == 1


@pytest.mark.asyncio
async def test_fetch_order_data_success():
    mock_response = {
        "symbol": "AAPL",
        "filled_avg_price": 150.0,
        "side": "buy",
        "trading_agent_reasonings": "RSI oversold",
    }

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json = MagicMock(return_value=mock_response)
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp

        result = await _fetch_order_data("order123", "user123")

        assert result["symbol"] == "AAPL"
        assert result["filled_avg_price"] == 150.0


@pytest.mark.asyncio
async def test_get_trade_history_details_success():
    mock_raw_data = {
        "symbol": "AAPL",
        "filled_avg_price": 150.0,
        "side": "buy",
        "trading_agent_reasonings": "RSI oversold",
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
async def test_get_trade_history_details_truncation():
    # Long reasoning (more than 1500 chars)
    long_reasoning = "X" * 2000
    mock_raw_data = {
        "symbol": "AAPL",
        "filled_avg_price": 150.0,
        "side": "buy",
        "trading_agent_reasonings": long_reasoning,
    }

    with patch(
        "app.services.tools.trade_history._fetch_order_data", new_callable=AsyncMock
    ) as mock_fetch:
        mock_fetch.return_value = mock_raw_data

        config = {"metadata": {"user_id": "user123"}}
        result = await get_trade_history_details.ainvoke(
            {"order_id": "order123"}, config=config
        )

        assert len(result.reasoning) < 2000
        assert "[Truncated for brevity]" in result.reasoning


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


@pytest.mark.asyncio
async def test_fetch_raw_trade_history_success():
    mock_response = [{"id": "1", "symbol": "AAPL"}]
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json = MagicMock(return_value=mock_response)
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        result = await _fetch_raw_trade_history("2024-01-01", "2024-01-02", "user123")
        assert result == mock_response


def test_transform_to_order_summaries():
    raw_data = [
        {
            "id": "ORD1",
            "symbol": "TSLA",
            "side": "buy",
            "filled_avg_price": 200.0,
            "created_at": "2024-01-01",
        }
    ]
    summaries = _transform_to_order_summaries(raw_data)
    assert len(summaries) == 1
    assert summaries[0].id == "ORD1"


@pytest.mark.asyncio
async def test_get_trade_history_list_success():
    mock_raw = [{"id": "1", "symbol": "AAPL"}]
    with patch(
        "app.services.tools.trade_history_list._fetch_raw_trade_history",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = mock_raw
        config = {"metadata": {"user_id": "user123"}}
        result = await get_trade_history_list.ainvoke(
            {"after": "2024-01-01", "until": "2024-01-02"}, config=config
        )
        assert len(result.orders) == 1
        assert result.orders[0].id == "1"


@pytest.mark.asyncio
async def test_get_trade_history_list_failure():
    with patch(
        "app.services.tools.trade_history_list._fetch_raw_trade_history",
        side_effect=Exception("API Error"),
    ):
        config = {"metadata": {"user_id": "user123"}}
        with pytest.raises(Exception) as excinfo:
            await get_trade_history_list.ainvoke(
                {"after": "2024-01-01", "until": "2024-01-02"}, config=config
            )
        assert "Unable to retrieve trade history" in str(excinfo.value)


@pytest.mark.asyncio
async def test_get_trade_history_list_truncation():
    # Create 25 mock orders (more than the MAX_TRADES limit of 20)
    mock_raw = [{"id": str(i), "symbol": "AAPL"} for i in range(25)]
    with patch(
        "app.services.tools.trade_history_list._fetch_raw_trade_history",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = mock_raw
        config = {"metadata": {"user_id": "user123"}}
        result = await get_trade_history_list.ainvoke(
            {"after": "2024-01-01", "until": "2024-01-02"}, config=config
        )
        assert len(result.orders) == 20
        assert result.total_count == 25
        assert result.truncated is True
        assert "Showing the first 20 of 25 total trades" in result.message


@pytest.mark.asyncio
async def test_fetch_news_from_api_ticker_query():
    mock_response = [{"metadata": {"headline": "Ticker news"}}]
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json = MagicMock(return_value=mock_response)
    mock_resp.raise_for_status = MagicMock()

    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = mock_resp

    result = await _fetch_news_from_api(
        client, "AAPL news", ["AAPL"], False, None, None
    )
    assert result == mock_response


@pytest.mark.asyncio
async def test_get_general_news_no_results():
    with patch(
        "app.services.tools.general_news._fetch_news_from_api", new_callable=AsyncMock
    ) as mock_fetch:
        mock_fetch.return_value = []
        result = await get_general_news.ainvoke({"query": "nothing"})
        assert "No relevant news found" in result["context"]


@pytest.mark.asyncio
async def test_get_general_news_http_error():
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 500
    mock_resp.text = "Error"

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.HTTPStatusError(
            "Err", request=MagicMock(), response=mock_resp
        )
        result = await get_general_news.ainvoke({"query": "market"})
        assert "API Error: 500" in result["context"]


@pytest.mark.asyncio
async def test_get_general_news_network_error():
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.RequestError("Err")
        result = await get_general_news.ainvoke({"query": "market"})
        assert "Network Error" in result["context"]
