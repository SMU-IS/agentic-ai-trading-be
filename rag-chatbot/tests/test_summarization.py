from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import (
    HumanMessage,
    RemoveMessage,
    SystemMessage,
)

from app.services.ai_agent.nodes.llm_chat import llm_chat_node
from app.services.ai_agent.nodes.summarise import summarise_node
from app.services.ai_agent.state import AgentState


@pytest.mark.asyncio
async def test_summarise_node_below_threshold():
    """Test that summarise_node does nothing if below threshold."""

    state: AgentState = {
        "messages": [HumanMessage(content="hi", id="1")],
        "summary": "",
    }
    llm = AsyncMock()

    result = await summarise_node(state, llm)

    assert result == {}
    llm.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_summarise_node_exceeds_threshold():
    """Test that summarise_node triggers and returns RemoveMessages and a new summary."""

    # Create 7 messages to exceed the threshold of 6
    messages = [HumanMessage(content=f"msg {i}", id=str(i)) for i in range(7)]
    state: AgentState = {"messages": messages, "summary": "Old summary"}

    # Mock LLM response
    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value = MagicMock(content="This is the new summary.")

    result = await summarise_node(state, mock_llm)

    # Assertions
    assert "summary" in result
    assert result["summary"] == "This is the new summary."
    assert "messages" in result

    # It should summarise everything EXCEPT the last 2 (indices 0 to 4)
    # So it should return 5 RemoveMessage objects
    assert len(result["messages"]) == 5
    assert all(isinstance(m, RemoveMessage) for m in result["messages"])

    # Verify the IDs to be removed
    removed_ids = [m.id for m in result["messages"]]
    assert removed_ids == ["0", "1", "2", "3", "4"]


@pytest.mark.asyncio
async def test_llm_chat_node_includes_summary():
    """Test that llm_chat_node includes the summary in the system prompt."""

    state: AgentState = {
        "messages": [HumanMessage(content="What is my order?", id="1")],
        "summary": "User is asking about order 123.",
    }

    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value = MagicMock(content="Your order is processing.")

    system_prompt = "You are a helpful assistant."

    await llm_chat_node(state, mock_llm, system_prompt)

    # Check the call to LLM
    called_messages = mock_llm.ainvoke.call_args[0][0]
    system_msg = called_messages[0]

    assert isinstance(system_msg, SystemMessage)
    assert "CONTEXT SUMMARY: User is asking about order 123." in system_msg.content
    assert "You are a helpful assistant." in system_msg.content


@pytest.mark.asyncio
async def test_summarise_node_fails_gracefully():
    """Test that summarise_node returns empty dict if LLM fails."""

    messages = [HumanMessage(content=f"msg {i}", id=str(i)) for i in range(10)]
    state: AgentState = {"messages": messages, "summary": ""}

    mock_llm = AsyncMock()
    mock_llm.ainvoke.side_effect = Exception("API Down")

    result = await summarise_node(state, mock_llm)
    assert result == {}
