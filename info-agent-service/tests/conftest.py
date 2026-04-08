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
