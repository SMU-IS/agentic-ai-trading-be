import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from app.services.ai_agent.nodes.trade_history import trade_history_node
from app.services.ai_agent.state import AgentState
from app.schemas.chat import TradeHistorySearch

@pytest.mark.asyncio
async def test_trade_history_node_defaults_to_30_days():
    # Setup state without order_id or date range, just ticker
    state: AgentState = {
        "messages": [HumanMessage(content="why u sell google")],
        "order_id": None,
    }
    
    # Mock LLM to extract ticker and provide default 30-day range
    now = datetime.now()
    thirty_days_ago = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    today = now.strftime("%Y-%m-%d")
    
    llm = MagicMock()
    structured_llm = AsyncMock()
    mock_extracted = TradeHistorySearch(
        ticker="GOOGL",
        after=thirty_days_ago, # Defaulted by LLM based on instructions
        until=today,
        order_id=None
    )
    structured_llm.ainvoke.return_value = mock_extracted
    llm.with_structured_output.return_value = structured_llm
    
    # Mock LLM.ainvoke for final formatting
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="Technical breakdown at resistance"))
    
    # Mock _get_trade_history_list to return one matching order
    mock_orders = [
        {"id": "ORD_G_1", "symbol": "GOOGL", "side": "sell", "created_at": today}
    ]
    
    # Mock get_trade_history_details to return order details
    from app.schemas.order_details import OrderDetailsResponse
    mock_details = OrderDetailsResponse(
        ticker="GOOGL",
        action="sell",
        entry_price=150.0,
        reasoning="Technical breakdown at resistance"
    )
    
    with patch("app.services.ai_agent.nodes.trade_history._get_trade_history_list", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = mock_orders
        
        with patch("app.services.ai_agent.nodes.trade_history.get_trade_history_details", new_callable=AsyncMock) as mock_tool:
            mock_tool.ainvoke.return_value = mock_details
            
            config = {"metadata": {"user_id": "test-user"}}
            result = await trade_history_node(state, config, llm=llm)
            
            # Verify results
            system_msg = result.get("messages", [])[0]
            assert "Technical breakdown at resistance" in system_msg.content
            # Ensure _get_trade_history_list was called with the 30-day range
            mock_list.assert_called_once_with(thirty_days_ago, today, "test-user")
