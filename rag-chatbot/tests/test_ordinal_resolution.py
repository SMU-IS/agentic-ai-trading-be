from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.schemas.chat import TradeHistorySearch
from app.services.ai_agent.nodes.trade_history import trade_history_node
from app.services.ai_agent.state import AgentState


@pytest.mark.asyncio
async def test_trade_history_node_resolves_ordinal_selection():
    # Setup state where user refers to 'the first one'
    # History includes the list of orders previously shown by the AI
    state: AgentState = {
        "messages": [
            HumanMessage(content="why did u sell google last week"),
            AIMessage(
                content="I found 2 orders for **GOOGL**: Which one are you interested in?\n\n1. **SELL** GOOGL on 2026-04-01 (ID: `ORD123`)\n2. **SELL** GOOGL on 2026-04-02 (ID: `ORD789`)"
            ),
            HumanMessage(content="the first one"),
        ],
        "order_id": None,
    }

    # Mock LLM to resolve 'the first one' to 'ORD123'
    llm = MagicMock()
    structured_llm = AsyncMock()
    mock_extracted = TradeHistorySearch(
        order_id="ORD123"  # The LLM successfully resolves the reference
    )
    structured_llm.ainvoke.return_value = mock_extracted
    llm.with_structured_output.return_value = structured_llm

    # Mock get_trade_history_details to return order details for ORD123
    from app.schemas.order_details import OrderDetailsResponse

    mock_details = OrderDetailsResponse(
        ticker="GOOGL", action="sell", entry_price=150.0, reasoning="RSI was overbought"
    )

    with patch(
        "app.services.ai_agent.nodes.trade_history.get_trade_history_details",
        new_callable=AsyncMock,
    ) as mock_tool:
        mock_tool.ainvoke.return_value = mock_details

        config = {"metadata": {"user_id": "test-user"}}
        result = await trade_history_node(state, config, llm=llm)

        # Verify results
        assert result["order_id"] == "ORD123"
        system_msg = result["messages"][0]
        assert "RSI was overbought" in system_msg.content
        # Ensure we didn't try to call _get_trade_history_list again since we had the ID
        mock_tool.ainvoke.assert_called_once_with({"order_id": "ORD123"}, config=config)
