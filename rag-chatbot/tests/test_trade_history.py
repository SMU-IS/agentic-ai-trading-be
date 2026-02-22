import pytest
from unittest.mock import patch, AsyncMock
from app.services.tools.trade_history import get_trade_history_details
from app.schemas.order_details import OrderDetailsResponse

@pytest.mark.asyncio
async def test_get_trade_history_details_success():

    mock_order_data = (
        "AAPL",
        150.0,
        "BUY",
        "Risk low",
        "None",
        "Strong RSI signal"
    )
    

    with patch("app.services.tools.trade_history.get_order_details", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_order_data
        
        result = await get_trade_history_details.ainvoke({
            "query": "Why did we buy AAPL?",
            "order_id": "order_123"
        })
        
        assert isinstance(result, OrderDetailsResponse)
        assert result.ticker == "AAPL"
        assert result.entry_price == 150.0
        assert result.action == "BUY"
        assert result.reasoning == "Strong RSI signal"
        mock_get.assert_called_once_with("order_123")

@pytest.mark.asyncio
async def test_get_trade_history_details_failure():
    with patch("app.services.tools.trade_history.get_order_details", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = Exception("API Error")
        
        with pytest.raises(Exception) as excinfo:
            await get_trade_history_details.ainvoke({
                "query": "Why did we buy AAPL?",
                "order_id": "order_123"
            })
        
        assert "Unable to retrieve trade history details for order order_123" in str(excinfo.value)
