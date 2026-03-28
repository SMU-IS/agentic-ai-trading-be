from langchain_core.messages import AIMessage, HumanMessage

from app.services.ai_agent.nodes.clarification import clarification_node
from app.services.ai_agent.state import AgentState


def test_clarification_node_returns_message():
    """Test that clarification_node returns the expected clarification message."""
    state: AgentState = {
        "messages": [HumanMessage(content="Check my order status")],
        "query": "Check my order status",
        "variables": {},
    }

    result = clarification_node(state)

    assert "messages" in result
    assert len(result["messages"]) == 1
    assert isinstance(result["messages"][0], AIMessage)
    assert "clarify" in result["messages"][0].content.lower()


def test_clarification_node_updates_variables():
    """Test that clarification_node updates the requires_clarification flag."""
    state: AgentState = {
        "messages": [HumanMessage(content="Help me")],
        "variables": {"existing_var": "value"},
    }

    result = clarification_node(state)

    assert "variables" in result
    assert result["variables"]["requires_clarification"] is True
    assert result["variables"]["existing_var"] == "value"


def test_clarification_node_handles_none_variables():
    """Test that clarification_node handles state with None variables."""
    state: AgentState = {
        "messages": [HumanMessage(content="Help me")],
        "variables": None,
    }

    result = clarification_node(state)

    assert "variables" in result
    assert result["variables"]["requires_clarification"] is True
