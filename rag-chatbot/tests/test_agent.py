from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.services.graph.chat_workflow import ChatWorkflow
from app.services.graph.state import AgentState


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    # Mock bind_tools to return a specific mock for bound tools
    mock_bound = MagicMock()
    llm.bind_tools.return_value = mock_bound
    return llm


@pytest.fixture
def agent_graph(mock_llm):
    return ChatWorkflow(llm=mock_llm, tools=[], system_prompt="Test Prompt")


@pytest.mark.asyncio
async def test_call_model(agent_graph, mock_llm):
    # Setup mock response for the BOUND llm
    mock_bound = mock_llm.bind_tools.return_value
    mock_bound.ainvoke = AsyncMock(return_value=AIMessage(content="Hello!", response_metadata={}))

    state: AgentState = {
        "messages": [HumanMessage(content="Hi")],
        "summary": "Previous summary",
    }

    config = {"metadata": {"user_id": "test-user"}}

    result = await agent_graph._call_model(state, config)

    assert len(result["messages"]) == 1
    assert result["messages"][0].content == "Hello!"

    # Verify BOUND LLM was called with dynamic system prompt including summary
    args, _ = mock_bound.ainvoke.call_args
    system_msg = args[0][0]
    assert "Test Prompt" in system_msg.content
    assert "test-user" in system_msg.content
    assert "Previous summary" in system_msg.content
    assert "### RESPONSE GUIDELINES" in system_msg.content


@pytest.mark.asyncio
async def test_summarize_conversation_no_trigger(agent_graph):
    state: AgentState = {
        "messages": [HumanMessage(content="Hi")] * 5,
        "summary": "",
    }
    result = await agent_graph._summarize_conversation(state)
    assert result["summary"] == ""
    assert "messages" not in result


@pytest.mark.asyncio
async def test_summarize_conversation_trigger(agent_graph, mock_llm):
    mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="New Summary"))

    # Create 15 messages to trigger summarization (threshold is 12)
    messages = [HumanMessage(content=f"msg {i}", id=str(i)) for i in range(15)]
    state: AgentState = {
        "messages": messages,
        "summary": "Old Summary",
    }

    result = await agent_graph._summarize_conversation(state)

    assert result["summary"] == "New Summary"
    assert "messages" in result
    # We kept 6 messages, so we should have removed 15 - 6 = 9 messages
    assert len(result["messages"]) == 9
    from langchain_core.messages import RemoveMessage

    assert isinstance(result["messages"][0], RemoveMessage)


@pytest.mark.asyncio
async def test_summarize_conversation_trigger_by_length(agent_graph, mock_llm):
    mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="New Summary"))

    # Create 10 messages but one is very large (total > 4000 chars)
    # We need more than 6 total messages to see removal
    messages = [HumanMessage(content=f"msg {i}", id=str(i)) for i in range(9)]
    messages.append(HumanMessage(content="X" * 5000, id="large"))

    state: AgentState = {
        "messages": messages,
        "summary": "Old Summary",
    }
    result = await agent_graph._summarize_conversation(state)

    assert result["summary"] == "New Summary"
    assert "messages" in result
    # We kept 6 messages, so we removed 10 - 6 = 4 messages
    assert len(result["messages"]) == 4


def test_workflow_structure(agent_graph):
    # Verify nodes exist in the graph
    nodes = agent_graph.graph.get_graph().nodes
    assert "agent" in nodes
    assert "tools" in nodes
    assert "summarize" in nodes
