import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock
from app.main import app

client = TestClient(app)

@pytest.mark.asyncio
async def test_get_user_threads_success():
    # Setup mock data with a datetime object for updated_at
    mock_updated_at = datetime(2026, 3, 22, 3, 32, 3, 182371, tzinfo=timezone.utc)
    mock_threads = [
        {
            "thread_id": "thread_1",
            "title": "Test Thread",
            "updated_at": mock_updated_at
        }
    ]
    
    # Mock bot_memory.aget_user_threads
    mock_bot_memory = AsyncMock()
    mock_bot_memory.aget_user_threads.return_value = mock_threads
    
    # Inject mock into app state
    app.state.bot_memory = mock_bot_memory
    
    # Execute request
    # Note: root_path is /api/v1/rag, so the endpoint is /threads
    response = client.get("/threads", headers={"x-user-id": "user_123"})
    
    # Assert
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["thread_id"] == "thread_1"
    assert data[0]["title"] == "Test Thread"
    # Pydantic should serialize datetime to ISO string
    assert "2026-03-22T03:32:03.182371Z" in data[0]["updated_at"] or "2026-03-22T03:32:03.182371+00:00" in data[0]["updated_at"]
