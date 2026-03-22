from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent_bot_service import AgentBotService


@pytest.fixture
def mock_dependencies():
    with (
        patch("app.services.agent_bot_service.RedisService") as mock_redis,
        patch("app.services.agent_bot_service.S3ConfigService") as mock_s3,
        patch("app.services.agent_bot_service.ChatWorkflow") as mock_chat_workflow,
    ):
        yield {
            "redis": mock_redis.return_value,
            "s3": mock_s3.return_value,
            "ChatWorkflow": mock_chat_workflow,
        }


@pytest.fixture
def agent_bot_service(mock_dependencies):
    llm = MagicMock()
    checkpointer = MagicMock()
    return AgentBotService(llm, checkpointer)


def test_get_llm_prompt_from_cache(agent_bot_service, mock_dependencies):
    # Setup
    mock_dependencies["redis"].get_cached_prompt.return_value = "cached prompt"

    # Execute
    prompt = agent_bot_service._get_llm_prompt()

    # Assert
    assert prompt == "cached prompt"
    mock_dependencies["redis"].get_cached_prompt.assert_called_once()
    mock_dependencies["s3"].get_file_content.assert_not_called()


def test_get_llm_prompt_from_s3(agent_bot_service, mock_dependencies):
    # Setup
    mock_dependencies["redis"].get_cached_prompt.return_value = None
    mock_dependencies["s3"].get_file_content.return_value = "s3 prompt"

    # Execute
    prompt = agent_bot_service._get_llm_prompt()

    # Assert
    assert prompt == "s3 prompt"
    mock_dependencies["s3"].get_file_content.assert_called_once()
    mock_dependencies["redis"].set_cached_prompt.assert_called_once()


@pytest.mark.asyncio
async def test_get_chat_history(agent_bot_service):
    # Setup
    mock_msg = MagicMock()
    mock_msg.content = "Hello"
    mock_msg.type = "human"
    mock_msg.dict.return_value = {
        "content": "Hello",
        "type": "human",
        "response_metadata": {"created_at": "2023-01-01"},
    }

    mock_state = MagicMock()
    mock_state.checkpoint = {"channel_values": {"messages": [mock_msg]}}
    agent_bot_service.checkpointer.aget = AsyncMock(return_value=mock_state)

    # Execute
    history = await agent_bot_service.get_chat_history("session_123")

    # Assert
    assert len(history) == 1
    assert history[0]["content"] == "Hello"
    assert history[0]["type"] == "human"


def test_is_displayable(agent_bot_service):
    # Human message
    msg1 = MagicMock(content="Hello", type="human")
    assert agent_bot_service._is_displayable(msg1) is True

    # Empty message
    msg2 = MagicMock(content="", type="human")
    assert agent_bot_service._is_displayable(msg2) is False

    # Technical message
    msg3 = MagicMock(content="Some tool output", type="tool")
    assert agent_bot_service._is_displayable(msg3) is False

    # Summary message
    msg4 = MagicMock(content="This is a summary of the conversation", type="human")
    assert agent_bot_service._is_displayable(msg4) is False


def test_format_message(agent_bot_service):
    msg = MagicMock()
    msg.dict.return_value = {
        "content": "Hello",
        "type": "human",
        "response_metadata": {"created_at": "2023-01-01"},
    }

    formatted = agent_bot_service._format_message(msg)

    assert formatted == {
        "content": "Hello",
        "type": "human",
        "created_at": "2023-01-01",
    }


@pytest.mark.asyncio
async def test_invoke_agent_streaming(agent_bot_service, mock_dependencies):
    # Setup
    agent_bot_service._get_llm_prompt = MagicMock(return_value="prompt")
    mock_agent = MagicMock()
    mock_dependencies["ChatWorkflow"].return_value = mock_agent

    async def mock_astream_events(*args, **kwargs):
        yield {"event": "on_tool_start", "name": "test_tool", "data": {}}
        yield {"event": "on_chat_model_stream", "data": {"chunk": MagicMock(content="Hi")}}
        yield {"event": "on_chat_model_end", "data": {"output": "Hi there"}}

    mock_agent.graph.astream_events = mock_astream_events

    # Execute
    gen = agent_bot_service.invoke_agent("Hello", None, "user_123", "session_123")
    events = []
    async for event in gen:
        events.append(event)

    # Assert
    assert any("Searching test_tool..." in e for e in events)
    assert any('"token": "Hi"' in e for e in events)
    assert events[-1] == "data: [DONE]\n\n"
