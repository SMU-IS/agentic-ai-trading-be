import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import HumanMessage, SystemMessage

from app.services.ai_agent.chat_workflow import ChatWorkflow
from app.services.ai_agent.state import AgentState
from app.schemas.router_decision import RouterDecision
from app.schemas.chat import TradeHistoryRange

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
        confidence=0.9
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
    from app.services.ai_agent.nodes.trade_history_list import trade_history_list_node
    
    llm = MagicMock()
    # Mock LLM extraction of dates
    mock_trade_history_range = TradeHistoryRange(after="2026-03-29", until="2026-03-30")
    llm.with_structured_output.return_value.ainvoke = AsyncMock(
        return_value=mock_trade_history_range
    )
    
    # Mock tool call
    mock_tool_result = MagicMock()
    mock_tool_result.dict.return_value = {"orders": []}
    
    with patch("app.services.tools.trade_history_list.get_trade_history_list") as mock_tool:
        mock_tool.ainvoke = AsyncMock(return_value=mock_tool_result)
        
        state: AgentState = {
            "messages": [HumanMessage(content="show me the trades for the past 1 day")],
            "sender": "user",
            "order_id": None,
            "query": "show me the trades for the past 1 day",
            "variables": {},
            "metadata": {},
        }
        
        result = await trade_history_list_node(state, llm)
        assert "messages" in result
        assert isinstance(result["messages"][0], SystemMessage)
        assert '"orders": []' in result["messages"][0].content
