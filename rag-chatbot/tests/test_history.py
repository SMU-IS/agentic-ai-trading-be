from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph.message import add_messages

from app.services.ai_agent.nodes.llm_chat import llm_chat_node
from app.services.ai_agent.state import AgentState


def test_agent_state_message_addition():
    """Test that AgentState correctly appends messages using add_messages reducer."""

    state: AgentState = {
        "messages": [HumanMessage(content="Hello", id="1")],
    }

    new_messages = [AIMessage(content="Hi there", id="2")]
    updated_messages = add_messages(state["messages"], new_messages)

    assert len(updated_messages) == 2
    assert updated_messages[0].content == "Hello"
    assert updated_messages[1].content == "Hi there"


def test_agent_state_message_replacement():
    """Test that AgentState correctly replaces messages with same ID."""

    state: AgentState = {
        "messages": [AIMessage(content="Old content", id="1")],
    }

    # Message with same ID should replace
    new_messages = [AIMessage(content="New content", id="1")]

    updated_messages = add_messages(state["messages"], new_messages)

    assert len(updated_messages) == 1
    assert updated_messages[0].content == "New content"


@pytest.mark.asyncio
async def test_llm_chat_node_uses_history():
    """Test that llm_chat_node passes the full history to the LLM."""

    llm = AsyncMock()
    llm.ainvoke.return_value = AIMessage(content="I remember you.")

    system_prompt = "You are a helpful assistant."
    state: AgentState = {
        "messages": [
            HumanMessage(content="My name is Joshua"),
            AIMessage(content="Hello Joshua!"),
            HumanMessage(content="What is my name?"),
        ],
        "query": "What is my name?",
    }

    await llm_chat_node(state, llm, system_prompt)

    args, _ = llm.ainvoke.call_args
    sent_messages = args[0]

    assert len(sent_messages) == 4  # System + 3 from history
    assert isinstance(sent_messages[0], SystemMessage)
    assert sent_messages[0].content == system_prompt
    assert sent_messages[1].content == "My name is Joshua"
    assert sent_messages[2].content == "Hello Joshua!"
    assert sent_messages[3].content == "What is my name?"
