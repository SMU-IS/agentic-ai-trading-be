from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage

from app.services.agent_bot_service import AgentBotService


@pytest.fixture
def agent_bot_service():
    llm = AsyncMock()
    checkpointer = AsyncMock()
    return AgentBotService(llm, checkpointer)


@pytest.mark.asyncio
async def test_get_chat_history_with_checkpoint_tuple(agent_bot_service):
    """
    Test that get_chat_history correctly handles the CheckpointTuple
    returned by newer LangGraph versions.
    """
    # 1. Setup mock messages
    mock_msg = HumanMessage(content="Hello", id="msg1")

    # 2. Mock the CheckpointTuple returned by checkpointer.aget
    mock_state = MagicMock()
    # Newer LangGraph returns a CheckpointTuple where the state is in .checkpoint
    mock_state.checkpoint = {"channel_values": {"messages": [mock_msg]}}
    agent_bot_service.checkpointer.aget = AsyncMock(return_value=mock_state)

    # 3. Execute
    history = await agent_bot_service.get_chat_history("session_123")

    # 4. Assert
    assert len(history) == 1
    assert history[0]["content"] == "Hello"
    assert history[0]["type"] == "human"


@pytest.mark.asyncio
async def test_invoke_agent_initial_state(agent_bot_service):
    """
    Test that invoke_agent initializes the graph with the correct simplified state.
    """
    # Setup
    agent_bot_service._get_llm_prompt = MagicMock(return_value="prompt")
    agent_bot_service._generate_title = AsyncMock(return_value="title")

    mock_graph_wrapper = MagicMock()
    mock_graph = MagicMock()

    # Mock astream_events to be an async iterator
    async def empty_iterator(*args, **kwargs):
        if False:
            yield None

    mock_astream = AsyncMock(side_effect=empty_iterator)
    mock_graph.astream_events = mock_astream
    mock_graph_wrapper.graph = mock_graph

    with patch.object(
        agent_bot_service, "_get_agent_graph", return_value=mock_graph_wrapper
    ):
        # Execute
        gen = agent_bot_service.invoke_agent("Hello", None, "user_123", "session_123")
        async for _ in gen:
            pass

        # Capture the initial state passed to astream_events
        args, kwargs = mock_astream.call_args
        initial_state = args[0]
        config = kwargs.get("config", {})

        # Assert state contains messages (summary is NOT reset here to preserve it across turns)
        assert "messages" in initial_state
        assert "summary" not in initial_state
        assert len(initial_state) == 1
        assert initial_state["messages"][0].content == "Hello"

        # Assert metadata contains user_id and title
        assert config["metadata"]["user_id"] == "user_123"
        assert config["metadata"]["title"] == "title"
