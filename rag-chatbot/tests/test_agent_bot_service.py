import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from app.services.agent_bot_service import AgentBotService


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.ainvoke = AsyncMock()
    return llm


@pytest.fixture
def mock_checkpointer():
    return MagicMock()


@pytest.fixture
def service(mock_llm, mock_checkpointer):
    with (
        patch("app.services.agent_bot_service.get_redis_service"),
        patch("app.services.agent_bot_service.S3ConfigService"),
    ):
        return AgentBotService(llm=mock_llm, checkpointer=mock_checkpointer)


def test_is_displayable(service):
    # Tool message should not be displayable
    tool_msg = MagicMock(spec=AIMessage)
    tool_msg.content = "some tool output"
    tool_msg.type = "tool"
    assert service._is_displayable(tool_msg) is False

    # Empty message should not be displayable
    empty_msg = MagicMock(spec=AIMessage)
    empty_msg.content = "  "
    empty_msg.type = "ai"
    assert service._is_displayable(empty_msg) is False

    # Regular AI message should be displayable
    ai_msg = MagicMock(spec=AIMessage)
    ai_msg.content = "Hello user"
    ai_msg.type = "ai"
    assert service._is_displayable(ai_msg) is True


@pytest.mark.asyncio
async def test_process_event_on_tool_start(service):
    event = {"event": "on_tool_start", "name": "get_news"}
    streamed_ids = set()

    chunks = []
    async for chunk in service._process_event(event, streamed_ids):
        chunks.append(chunk)

    assert len(chunks) == 1
    assert "Searching get_news" in chunks[0]


@pytest.mark.asyncio
async def test_process_event_on_chat_model_stream(service):
    chunk_mock = MagicMock()
    chunk_mock.content = "part of response"
    chunk_mock.id = "msg1"

    event = {
        "event": "on_chat_model_stream",
        "tags": ["user_response"],
        "data": {"chunk": chunk_mock},
    }
    streamed_ids = set()

    chunks = []
    async for chunk in service._process_event(event, streamed_ids):
        chunks.append(chunk)

    assert len(chunks) == 1
    data = json.loads(chunks[0].replace("data: ", ""))
    assert data["token"] == "part of response"
    assert "msg1" in streamed_ids


def test_format_message(service):
    msg = MagicMock()
    msg.dict.return_value = {
        "content": "test content",
        "type": "ai",
        "response_metadata": {"created_at": "2024-01-01"},
    }

    formatted = service._format_message(msg)
    assert formatted["content"] == "test content"
    assert formatted["type"] == "ai"
    assert formatted["created_at"] == "2024-01-01"
