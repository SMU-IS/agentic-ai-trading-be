import pytest
from unittest.mock import AsyncMock, MagicMock
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.services.ai_agent.chat_workflow import ChatWorkflow
from app.services.ai_agent.state import AgentState
from app.services.ai_agent.nodes import extract_order_id_node, format_response_node
from app.schemas.router_decision import RouterDecision


@pytest.fixture
def agent_graph():
    llm = MagicMock()
    return ChatWorkflow(llm=llm, tools=[], system_prompt="Test Prompt")


def test_extract_order_id_regex():
    # Test different order ID formats
    queries = [
        ("Please check order ID ABC123", "ABC123"),
        ("What is the status of symbol XYZ789?", "XYZ789"),
        ("id: 123456", "123456"),
        ("transaction 999", "999"),
        ("General question without id", None),
    ]

    for query, expected_id in queries:
        state: AgentState = {
            "messages": [HumanMessage(content=query)],
            "sender": "user",
            "order_id": None,
            "query": "",
            "variables": {},
            "metadata": {},
        }
        result = extract_order_id_node(state)
        assert result["order_id"] == expected_id
        assert result["query"] == query


@pytest.mark.asyncio
async def test_route_logic(agent_graph):
    # Route to trade_history if requested
    mock_decision = RouterDecision(next_node="trade_history", reasoning="User wants status", confidence=0.9)
    agent_graph.llm.with_structured_output.return_value.ainvoke = AsyncMock(
        return_value=mock_decision
    )

    state: AgentState = {
        "messages": [HumanMessage(content="What is my order status?")],
        "sender": "user",
        "order_id": "123",
        "query": "",
        "variables": {},
        "metadata": {},
    }
    assert await agent_graph._route(state) == "trade_history"

    # Route to general_news
    mock_decision_news = RouterDecision(next_node="general_news", reasoning="User wants news", confidence=0.9)
    agent_graph.llm.with_structured_output.return_value.ainvoke = AsyncMock(
        return_value=mock_decision_news
    )

    state_news: AgentState = {
        "messages": [HumanMessage(content="Any news on AAPL?")],
        "sender": "user",
        "order_id": None,
        "query": "",
        "variables": {},
        "metadata": {},
    }
    assert await agent_graph._route(state_news) == "general_news"


@pytest.mark.asyncio
async def test_format_response_json():
    # Test JSON formatting for ticker info
    content = '{"ticker": "AAPL", "action": "BUY", "entry_price": 150, "reasoning": "Bullish"}'
    state: AgentState = {
        "messages": [SystemMessage(content=content)],
        "sender": "agent",
        "order_id": "ORD123",
        "query": "",
        "variables": {},
        "metadata": {},
    }

    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="Order ID: ORD123, Ticker: AAPL, Action: BUY, Bullish"))

    result = await format_response_node(state, llm)
    formatted_content = result["messages"][0].content
    assert "Order ID: ORD123" in formatted_content
    assert "Ticker: AAPL" in formatted_content
    assert "Action: BUY" in formatted_content


@pytest.mark.asyncio
async def test_format_response_context():
    # Test "context" key extraction
    content = '{"context": "This is the relevant information."}'
    state: AgentState = {
        "messages": [SystemMessage(content=content)],
        "sender": "agent",
        "order_id": None,
        "query": "",
        "variables": {},
        "metadata": {},
    }

    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="This is the relevant information."))

    result = await format_response_node(state, llm)
    assert result["messages"][0].content == "This is the relevant information."
