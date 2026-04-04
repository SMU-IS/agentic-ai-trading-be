import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from app.services.ai_agent.nodes.trade_history import trade_history_node
from app.services.ai_agent.state import AgentState
from app.schemas.chat import TradeHistorySearch

@pytest.mark.asyncio
async def test_trade_history_node_finds_order_by_ticker():
    # Setup state without order_id but with ticker/date info in messages
    state: AgentState = {
        "messages": [HumanMessage(content="why did u sell google last week")],
        "order_id": None,
    }
    
    # Mock LLM to extract ticker and dates
    llm = MagicMock()
    structured_llm = AsyncMock()
    mock_extracted = TradeHistorySearch(
        ticker="GOOGL",
        after="2026-03-27",
        until="2026-04-03"
    )
    structured_llm.ainvoke.return_value = mock_extracted
    llm.with_structured_output.return_value = structured_llm
    
    # Mock _get_trade_history_list to return one matching order
    mock_orders = [
        {"id": "ORD123", "symbol": "GOOGL", "side": "sell", "created_at": "2026-04-01"},
        {"id": "ORD456", "symbol": "AAPL", "side": "buy", "created_at": "2026-04-01"}
    ]
    
    # Mock get_trade_history_details to return order details
    from app.schemas.order_details import OrderDetailsResponse
    mock_details = OrderDetailsResponse(
        ticker="GOOGL",
        action="sell",
        entry_price=150.0,
        reasoning="RSI was overbought"
    )
    
    with patch("app.services.ai_agent.nodes.trade_history._get_trade_history_list", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = mock_orders
        
        # Patch the tool's ainvoke method in the node module where it was imported
        with patch("app.services.ai_agent.nodes.trade_history.get_trade_history_details", new_callable=AsyncMock) as mock_tool:
            mock_tool.ainvoke.return_value = mock_details
            
            config = {"metadata": {"user_id": "test-user"}}
            result = await trade_history_node(state, config, llm=llm)
            
            # Verify results
            assert "messages" in result
            system_msg = result.get("messages", [])[0]
            assert isinstance(system_msg, SystemMessage)
            content = json.loads(system_msg.content)
            assert content["ticker"] == "GOOGL"
            assert content["reasoning"] == "RSI was overbought"
            assert result["order_id"] == "ORD123"

@pytest.mark.asyncio
async def test_trade_history_node_multiple_orders_found():
    state: AgentState = {
        "messages": [HumanMessage(content="why did u sell google last week")],
        "order_id": None,
    }
    
    llm = MagicMock()
    structured_llm = AsyncMock()
    mock_extracted = TradeHistorySearch(
        ticker="GOOGL",
        after="2026-03-27",
        until="2026-04-03"
    )
    structured_llm.ainvoke.return_value = mock_extracted
    llm.with_structured_output.return_value = structured_llm
    
    # Mock _get_trade_history_list to return two matching orders
    mock_orders = [
        {"id": "ORD123", "symbol": "GOOGL", "side": "sell", "created_at": "2026-04-01"},
        {"id": "ORD789", "symbol": "GOOGL", "side": "sell", "created_at": "2026-04-02"}
    ]
    
    with patch("app.services.ai_agent.nodes.trade_history._get_trade_history_list", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = mock_orders
        
        config = {"metadata": {"user_id": "test-user"}}
        result = await trade_history_node(state, config, llm=llm)
        
        assert "messages" in result
        ai_msg = result["messages"][0]
        assert isinstance(ai_msg, AIMessage)
        assert f"found {len(mock_orders)} orders for **GOOGL**" in ai_msg.content
        assert "ORD123" in ai_msg.content
        assert "ORD789" in ai_msg.content

@pytest.mark.asyncio
async def test_trade_history_node_no_orders_found():
    state: AgentState = {
        "messages": [HumanMessage(content="why did u sell google last week")],
        "order_id": None,
    }
    
    llm = MagicMock()
    structured_llm = AsyncMock()
    mock_extracted = TradeHistorySearch(
        ticker="GOOGL",
        after="2026-03-27",
        until="2026-04-03"
    )
    structured_llm.ainvoke.return_value = mock_extracted
    llm.with_structured_output.return_value = structured_llm
    
    with patch("app.services.ai_agent.nodes.trade_history._get_trade_history_list", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = [] # No orders
        
        config = {"metadata": {"user_id": "test-user"}}
        result = await trade_history_node(state, config, llm=llm)
        
        assert "messages" in result
        ai_msg = result["messages"][0]
        assert isinstance(ai_msg, AIMessage)
        assert "couldn't find any trades for **GOOGL**" in ai_msg.content
