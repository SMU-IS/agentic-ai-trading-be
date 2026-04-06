import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock
from app.main import app
from app.services.query_qdrant import QueryQdrantService

client = TestClient(app)

@pytest.fixture
def mock_query_service():
    mock = MagicMock(spec=QueryQdrantService)
    app.dependency_overrides[QueryQdrantService] = lambda: mock
    yield mock
    app.dependency_overrides.clear()

def test_get_latest_news_success(mock_query_service):
    mock_data = [
        {
            "topic_id": "topic_latest_123",
            "text_content": "Latest market trends.",
            "metadata": {"timestamp": "2026-04-04T12:00:00Z"}
        }
    ]
    
    mock_query_service.retrieve_latest_news = AsyncMock(return_value=mock_data)
    
    response = client.get("/news/latest?limit=10")
    
    assert response.status_code == 200
    json_response = response.json()
    assert json_response["status"] == "success"
    assert json_response["count"] == 1
    assert json_response["data"][0]["topic_id"] == "topic_latest_123"
    
    mock_query_service.retrieve_latest_news.assert_called_once_with(limit=10)

def test_get_latest_news_error(mock_query_service):
    mock_query_service.retrieve_latest_news.side_effect = Exception("Internal error")

    response = client.get("/news/latest")
    
    assert response.status_code == 500
    assert "Internal error" in response.json()["detail"]
