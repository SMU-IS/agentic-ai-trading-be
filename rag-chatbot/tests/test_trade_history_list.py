from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage

from app.schemas.chat import TradeHistoryRange
from app.schemas.router_decision import RouterDecision
from app.services.ai_agent.chat_workflow import ChatWorkflow
from app.services.ai_agent.state import AgentState


@pytest.fixture
def agent_graph():
    llm = MagicMock()
    return ChatWorkflow(llm=llm, tools=[], system_prompt="Test Prompt")


@pytest.mark.asyncio
async def test_route_to_trade_history_list(agent_graph):
    # Route to trade_history_list if requested
    mock_decision = RouterDecision(
        next_node="trade_history_list",
        reasoning="User wants trade history for a period",
        confidence=0.9,
    )
    agent_graph.llm.with_structured_output.return_value.ainvoke = AsyncMock(
        return_value=mock_decision
    )

    state: AgentState = {
        "messages": [HumanMessage(content="show me the trades for the past 1 day")],
        "sender": "user",
        "order_id": None,
        "query": "show me the trades for the past 1 day",
        "variables": {},
        "metadata": {},
    }
    assert await agent_graph._route(state) == "trade_history_list"


@pytest.mark.asyncio
async def test_trade_history_list_node_extraction():
    from langchain_core.messages import AIMessage

    from app.services.ai_agent.nodes.trade_history_list import trade_history_list_node

    llm = MagicMock()
    # Mock LLM extraction of dates
    mock_trade_history_range = TradeHistoryRange(after="2026-03-29", until="2026-03-30")
    llm.with_structured_output.return_value.ainvoke = AsyncMock(
        return_value=mock_trade_history_range
    )

    # Mock final formatting LLM call
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="You have no orders."))

    # Mock tool call
    mock_tool_result = MagicMock()
    # Updated to model_dump() for Pydantic V2
    mock_tool_result.model_dump.return_value = {"orders": []}

    with patch(
        "app.services.tools.trade_history_list.get_trade_history_list"
    ) as mock_tool:
        mock_tool.ainvoke = AsyncMock(return_value=mock_tool_result)

        state: AgentState = {
            "messages": [HumanMessage(content="show me the trades for the past 1 day")],
            "sender": "user",
            "order_id": None,
            "query": "show me the trades for the past 1 day",
            "variables": {},
            "metadata": {"user_id": "user123"},
        }

        config = {"metadata": {"user_id": "user123"}}
        result = await trade_history_list_node(state, config, llm)
        assert "messages" in result
        assert isinstance(result["messages"][0], AIMessage)
        assert "no orders" in result["messages"][0].content.lower()
