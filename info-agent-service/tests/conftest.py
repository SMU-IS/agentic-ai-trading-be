"""
conftest.py

Injects mock environment variables at module load time, before pytest begins
collecting and importing test modules.

This prevents pydantic_settings from raising a ValidationError when EnvConfig()
is instantiated at import time in app/core/config.py.
"""

import os
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.query import get_info_agent_service
from app.services.info_agent import InfoAgentService


@pytest.fixture
def mock_info_agent_service():
    service = MagicMock(spec=InfoAgentService)

    # Mock get_session_history
    mock_history = MagicMock()
    mock_history.messages = []
    service.get_session_history.return_value = mock_history

    # Mock ainvoke as an async generator
    async def mock_ainvoke(question, session_id):
        yield {"status": "Searching knowledge base..."}
        yield {"token": "Hello"}
        yield {"token": " World"}

    service.ainvoke = mock_ainvoke

    return service


@pytest.fixture
def client(mock_info_agent_service):
    # Override the dependency
    app.dependency_overrides[get_info_agent_service] = lambda: mock_info_agent_service
    with TestClient(app) as c:
        yield c
    # Clear overrides after test
    app.dependency_overrides.clear()


os.environ.setdefault("LLM_PROVIDER", "gemini")
os.environ.setdefault("LARGE_LANGUAGE_MODEL", "mock-model")
os.environ.setdefault("GROQ_API_KEY", "api-key")
os.environ.setdefault("NOMIC_API_KEY", "api-key")
os.environ.setdefault("TEXT_EMBEDDING_MODEL", "mock-model")
os.environ.setdefault("QDRANT_API_KEY", "mock-key")
os.environ.setdefault("QDRANT_URL", "http://mock/query")
os.environ.setdefault("QDRANT_COLLECTION_NAME", "mock")
