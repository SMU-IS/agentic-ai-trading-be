from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.services.graph.chat_workflow import ChatWorkflow
from app.services.graph.state import AgentState


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    # Mock bind_tools to return itself (or another mock)
    llm.bind_tools.return_value = llm
    return llm


@pytest.fixture
def agent_graph(mock_llm):
    return ChatWorkflow(llm=mock_llm, tools=[], system_prompt="Test Prompt")


@pytest.mark.asyncio
async def test_call_model(agent_graph, mock_llm):
    # Setup mock response
    mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="Hello!"))

    state: AgentState = {
        "messages": [HumanMessage(content="Hi")],
    }

    config = {"metadata": {"user_id": "test-user"}}

    result = await agent_graph._call_model(state, config)

    assert len(result["messages"]) == 1
    assert result["messages"][0].content == "Hello!"

    # Verify LLM was called with dynamic system prompt
    args, kwargs = mock_llm.ainvoke.call_args
    system_msg = args[0][0]
    assert "Test Prompt" in system_msg.content
    assert "test-user" in system_msg.content


def test_workflow_structure(agent_graph):
    # Verify nodes exist in the graph
    nodes = agent_graph.graph.get_graph().nodes
    assert "agent" in nodes
    assert "tools" in nodes
    assert "__start__" in nodes
