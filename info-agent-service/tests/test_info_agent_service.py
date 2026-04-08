from unittest.mock import MagicMock, patch

import pytest
from langchain_core.chat_history import InMemoryChatMessageHistory

from app.services.info_agent import InfoAgentService, store


@pytest.fixture
def clean_store():
    store.clear()
    yield
    store.clear()


def test_get_session_history_new_session(clean_store):
    # Mock settings to avoid initialization issues
    with (
        patch("app.services.info_agent.ChatGroq"),
        patch("app.services.info_agent.NomicEmbeddings"),
        patch("app.services.info_agent.QdrantClient"),
        patch("app.services.info_agent.QdrantVectorStore"),
    ):
        service = InfoAgentService()
        session_id = "test_session"
        history = service.get_session_history(session_id)

        assert isinstance(history, InMemoryChatMessageHistory)
        assert session_id in store
        assert "last_accessed" in store[session_id]


def test_get_session_history_existing_session(clean_store):
    with (
        patch("app.services.info_agent.ChatGroq"),
        patch("app.services.info_agent.NomicEmbeddings"),
        patch("app.services.info_agent.QdrantClient"),
        patch("app.services.info_agent.QdrantVectorStore"),
    ):
        service = InfoAgentService()
        session_id = "test_session"

        # Access first time
        history1 = service.get_session_history(session_id)
        last_accessed1 = store[session_id]["last_accessed"]

        # Access second time
        history2 = service.get_session_history(session_id)
        last_accessed2 = store[session_id]["last_accessed"]

        assert history1 is history2
        assert last_accessed2 >= last_accessed1


def test_session_cleanup(clean_store):
    with (
        patch("app.services.info_agent.ChatGroq"),
        patch("app.services.info_agent.NomicEmbeddings"),
        patch("app.services.info_agent.QdrantClient"),
        patch("app.services.info_agent.QdrantVectorStore"),
    ):
        service = InfoAgentService()

        # Add a session manually and make it old
        import time

        old_session_id = "old_session"
        store[old_session_id] = {
            "history": InMemoryChatMessageHistory(),
            "last_accessed": time.time() - 4000,  # More than 3600s
        }

        # Add a recent session
        recent_session_id = "recent_session"
        store[recent_session_id] = {
            "history": InMemoryChatMessageHistory(),
            "last_accessed": time.time(),
        }

        # Accessing any session should trigger cleanup
        service.get_session_history("any_session")

        assert old_session_id not in store
        assert recent_session_id in store


@pytest.mark.asyncio
async def test_ainvoke_success(clean_store):
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
            yield {"event": "on_retriever_start"}
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
        assert events[0] == {"status": "Searching knowledge base..."}
        assert events[1] == {"token": "hello"}
