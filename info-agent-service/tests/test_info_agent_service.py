import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.info_agent import InfoAgentService


def test_get_session_history_returns_redis_history():
    # Mock settings to avoid initialization issues
    with (
        patch("app.services.info_agent.ChatGroq"),
        patch("app.services.info_agent.NomicEmbeddings"),
        patch("app.services.info_agent.QdrantClient"),
        patch("app.services.info_agent.QdrantVectorStore"),
        patch("app.services.info_agent.RedisChatMessageHistory") as MockRedisHistory,
    ):
        service = InfoAgentService()
        session_id = "test_session"
        history = service.get_session_history(session_id)

        MockRedisHistory.assert_called_once()
        assert history == MockRedisHistory.return_value


def test_clear_session_history():
    with (
        patch("app.services.info_agent.ChatGroq"),
        patch("app.services.info_agent.NomicEmbeddings"),
        patch("app.services.info_agent.QdrantClient"),
        patch("app.services.info_agent.QdrantVectorStore"),
        patch("app.services.info_agent.RedisChatMessageHistory") as MockRedisHistory,
    ):
        service = InfoAgentService()
        session_id = "test_session"
        service.clear_session_history(session_id)

        MockRedisHistory.return_value.clear.assert_called_once()


@pytest.mark.asyncio
async def test_ainvoke_success():
    with (
        patch("app.services.info_agent.ChatGroq"),
        patch("app.services.info_agent.NomicEmbeddings"),
        patch("app.services.info_agent.QdrantClient"),
        patch("app.services.info_agent.QdrantVectorStore"),
        patch("app.services.info_agent.RunnableWithMessageHistory") as MockHistory,
    ):
        # Mock the chain with history events
        mock_instance = MockHistory.return_value

        async def mock_astream_events(*args, **kwargs):
            # Test retriever end to verify documents formatting
            mock_doc = MagicMock()
            mock_doc.metadata = {"source": "test.md"}
            mock_doc.page_content = "retrieved content"
            yield {"event": "on_retriever_end", "data": {"output": [mock_doc]}}

            yield {
                "event": "on_chat_model_stream",
                "data": {"chunk": MagicMock(content="hello")},
            }
            yield {"event": "on_chat_model_end", "data": {"output": "hello world"}}

        mock_instance.astream_events = mock_astream_events

        service = InfoAgentService()
        events = []
        async for event in service.ainvoke("hi", "session_1"):
            events.append(event)

        assert len(events) == 2

        # Check first event (retriever end thought)
        expected_thought = "<thought>Agent M: Retrieved the following sauce from the knowledge base:\n\n--- Source: test.md ---\nretrieved content</thought>"
        expected_first = f"data: {json.dumps({'reasoning_content': expected_thought})}\n\n"
        assert events[0] == expected_first

        # Check second event (token stream)
        expected_second = f"data: {json.dumps({'token': 'hello'})}\n\n"
        assert events[1] == expected_second
