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
    event = {
        "event": "on_tool_start",
        "name": "get_news",
        "data": {"input": {"query": "AAPL"}},
    }
    streamed_ids = set()

    chunks = []
    async for chunk in service._process_event(event, streamed_ids):
        chunks.append(chunk)

    assert len(chunks) == 1
    data = json.loads(chunks[0].replace("data: ", ""))
    assert "<thought>" in data["token"]
    assert "get_news" in data["token"]
    assert data["status"] == "searching"


@pytest.mark.asyncio
async def test_process_event_on_tool_end(service):
    event = {
        "event": "on_tool_end",
        "name": "get_news",
        "data": {"output": "Some news content"},
    }
    streamed_ids = set()

    chunks = []
    async for chunk in service._process_event(event, streamed_ids):
        chunks.append(chunk)

    assert len(chunks) == 1
    data = json.loads(chunks[0].replace("data: ", ""))
    assert "<thought>" in data["token"]
    assert "returned data" in data["token"]
    assert data["status"] == "completed"
    assert data["output"] == "Some news content"


@pytest.mark.asyncio
async def test_handle_token_stream_with_reasoning(service):
    chunk_mock = MagicMock()
    chunk_mock.content = ""
    chunk_mock.additional_kwargs = {"reasoning_content": "Analyzing market data..."}

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
    assert data["reasoning_content"] == "Analyzing market data..."
    assert data["token"] == "<thought>Analyzing market data...</thought>"


@pytest.mark.asyncio
async def test_process_event_on_chat_model_stream(service):
    chunk_mock = MagicMock()
    chunk_mock.content = "part of response"
    chunk_mock.id = "msg1"
    chunk_mock.additional_kwargs = {}
    chunk_mock.reasoning_content = "" # Fix: ensure it's a string, not a mock

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


@pytest.mark.asyncio
async def test_invoke_agent_success(service):
    # Setup mock graph
    mock_graph = AsyncMock()

    async def mock_astream_events(*args, **kwargs):
        yield {"event": "on_tool_start", "name": "test_tool", "data": {"input": {}}}
        yield {
            "event": "on_chat_model_stream",
            "tags": ["user_response"],
            "data": {"chunk": MagicMock(content="Hello", id="1", additional_kwargs={})},
        }

    mock_graph.astream_events = mock_astream_events
    service._get_agent_graph = MagicMock()
    service._get_agent_graph.return_value.graph = mock_graph
    service._generate_title = AsyncMock(return_value="title")

    chunks = []
    async for chunk in service.invoke_agent("query", None, "u1", "s1"):
        chunks.append(chunk)

    assert any("<thought>" in c and "test_tool" in c for c in chunks)
    assert any("Hello" in c for c in chunks)
    assert chunks[-1] == "data: [DONE]\n\n"


def test_format_message_dict(service):
    msg = {
        "content": "test content",
        "type": "human",
        "response_metadata": {"created_at": "2024-01-02"},
    }
    formatted = service._format_message(msg)
    assert formatted["content"] == "test content"
    assert formatted["type"] == "human"


@pytest.mark.asyncio
async def test_get_chat_history_no_state(service):
    service.checkpointer.aget = AsyncMock(return_value=None)
    history = await service.get_chat_history("empty_session")
    assert history == []


@pytest.mark.asyncio
async def test_process_event_on_chat_model_end(service):
    event = {
        "event": "on_chat_model_end",
        "tags": ["user_response"],
        "data": {"output": {"id": "out1", "content": "done"}},
    }
    streamed_ids = set()
    async for _ in service._process_event(event, streamed_ids):
        pass
    assert "out1" in streamed_ids


@pytest.mark.asyncio
async def test_process_event_on_chain_stream(service):
    msg = MagicMock()
    msg.type = "ai"
    msg.content = "chain output"
    msg.id = "c1"
    event = {"event": "on_chain_stream", "data": {"chunk": {"messages": [msg]}}}
    streamed_ids = set()
    chunks = []
    async for chunk in service._process_event(event, streamed_ids):
        chunks.append(chunk)
    assert any("chain output" in c for c in chunks)
    assert "c1" in streamed_ids
