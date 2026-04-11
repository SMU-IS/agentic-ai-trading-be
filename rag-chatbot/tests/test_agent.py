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

    # Create 10 messages
    messages = [HumanMessage(content=f"msg {i}") for i in range(10)]
    state: AgentState = {
        "messages": messages,
        "summary": "Previous summary",
    }

    config = {"metadata": {"user_id": "test-user"}}

    result = await agent_graph._call_model(state, config)

    assert len(result["messages"]) == 1
    assert result["messages"][0].content == "Hello!"

    # Verify BOUND LLM was called with windowed messages (last 10)
    args, _ = mock_bound.ainvoke.call_args
    sent_msgs = args[0]
    # 1 SystemMessage + 10 windowed messages = 11
    assert len(sent_msgs) == 11
    assert sent_msgs[1].content == "msg 0"
    assert sent_msgs[-1].content == "msg 9"
    
    system_msg = sent_msgs[0]
    assert "Test Prompt" in system_msg.content
    assert "### CURRENT SESSION INFO" in system_msg.content
    assert "- Today's Date:" in system_msg.content
    assert "- User ID: test-user" in system_msg.content
    assert "Previous summary" in system_msg.content
    assert "STRICT RULE" in system_msg.content


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

    # Create 20 messages to trigger summarization
    messages = [HumanMessage(content=f"msg {i}", id=str(i)) for i in range(20)]
    state: AgentState = {
        "messages": messages,
        "summary": "Old Summary",
        "last_summarized_id": None
    }

    result = await agent_graph._summarize_conversation(state)

    assert result["summary"] == "New Summary"
    # Incremental summarization doesn't delete messages anymore
    assert "messages" not in result
    # It should have summarized up to index 13 (20 - 6 - 1 = 13)
    assert result["last_summarized_id"] == "13"


@pytest.mark.asyncio
async def test_summarize_conversation_trigger_by_length(agent_graph, mock_llm):
    mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="New Summary"))

    # Create 10 messages but one is very large (total > 4000 chars)
    messages = [HumanMessage(content=f"msg {i}", id=str(i)) for i in range(9)]
    messages.append(HumanMessage(content="X" * 5000, id="large"))

    state: AgentState = {
        "messages": messages,
        "summary": "Old Summary",
        "last_summarized_id": None
    }
    result = await agent_graph._summarize_conversation(state)

    assert result["summary"] == "New Summary"
    assert "messages" not in result
    # It should have summarized up to index 3 (10 - 6 - 1 = 3)
    assert result["last_summarized_id"] == "3"


@pytest.mark.asyncio
async def test_call_model_no_tool_on_summary(agent_graph, mock_llm):
    """
    Verify that the AI can answer from context (summary) without calling tools.
    """
    mock_bound = mock_llm.bind_tools.return_value
    # Mock a direct textual response (no tool calls)
    mock_bound.ainvoke = AsyncMock(return_value=AIMessage(content="Here is your TLDR: The trade was a buy.", response_metadata={}))

    state: AgentState = {
        "messages": [HumanMessage(content="tldr?")],
        "summary": "The trade for MBAI was a buy at $1.67 due to a merger catalyst.",
    }

    config = {"metadata": {"user_id": "test-user"}}

    result = await agent_graph._call_model(state, config)

    assert result["messages"][0].content == "Here is your TLDR: The trade was a buy."
    
    # Verify no tool calls were attempted in this textual response
    assert not hasattr(result["messages"][0], "tool_calls") or not result["messages"][0].tool_calls


def test_workflow_structure(agent_graph):
    # Verify nodes exist in the graph
    nodes = agent_graph.graph.get_graph().nodes
    assert "agent" in nodes
    assert "tools" in nodes
    assert "summarize" in nodes
    
    # Verify edges (simplified check of graph structure)
    edges = agent_graph.graph.get_graph().edges
    # Convert edges to a list of (source, target) tuples for easier checking
    edge_pairs = [(e.source, e.target) for e in edges]
    
    # Check for direct tools -> agent edge
    assert ("tools", "agent") in edge_pairs
    # Check for start -> summarize -> agent path
    assert ("__start__", "summarize") in edge_pairs
    assert ("summarize", "agent") in edge_pairs
