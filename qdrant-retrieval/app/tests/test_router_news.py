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

def test_get_all_news_success(mock_query_service):
    mock_data = {
        "results": [
            {
                "topic_id": "topic_123",
                "text_content": "This is a sample news article about AI.",
                "metadata": {"source": "Reuters"}
            }
        ],
        "next_offset": "offset_456"
    }
    
    mock_query_service.retrieve_news = AsyncMock(return_value=mock_data)
    
    response = client.get("/news?limit=10")
    
    assert response.status_code == 200
    json_response = response.json()
    assert json_response["status"] == "success"
    assert json_response["count"] == 1
    assert json_response["next_offset"] == "offset_456"
    assert json_response["data"][0]["topic_id"] == "topic_123"
    
    mock_query_service.retrieve_news.assert_called_once_with(
        limit=10, 
        offset=None, 
        sort_by_recency=True,
        start_date=None,
        end_date=None
    )

def test_get_all_news_with_offset(mock_query_service):
    mock_data = {
        "results": [],
        "next_offset": None
    }
    
    mock_query_service.retrieve_news = AsyncMock(return_value=mock_data)
    
    response = client.get("/news?limit=5&offset=offset_abc")
    
    assert response.status_code == 200
    json_response = response.json()
    assert json_response["status"] == "success"
    assert json_response["count"] == 0
    assert json_response["next_offset"] is None
    

    mock_query_service.retrieve_news.assert_called_once_with(
        limit=5, 
        offset="offset_abc",
        sort_by_recency=True,
        start_date=None,
        end_date=None
    )

def test_get_news_with_date_filtering(mock_query_service):
    mock_data = {
        "results": [
            {
                "topic_id": "topic_789",
                "text_content": "Filtered news article.",
                "metadata": {"timestamp": "2026-04-01T10:00:00Z"}
            }
        ],
        "next_offset": None
    }
    
    mock_query_service.retrieve_news = AsyncMock(return_value=mock_data)
    
    start_date = "2026-04-01T00:00:00"
    end_date = "2026-04-02T23:59:59"
    response = client.get(f"/news?start_date={start_date}&end_date={end_date}")
    
    assert response.status_code == 200
    json_response = response.json()
    assert json_response["status"] == "success"
    assert json_response["count"] == 1
    
    from datetime import datetime
    mock_query_service.retrieve_news.assert_called_once_with(
        limit=50, 
        offset=None, 
        sort_by_recency=True,
        start_date=datetime.fromisoformat(start_date),
        end_date=datetime.fromisoformat(end_date)
    )

def test_get_news_invalid_date_format(mock_query_service):
    response = client.get("/news?start_date=invalid-date")
    
    assert response.status_code == 400
    assert "Invalid date format" in response.json()["detail"]

def test_get_all_news_error(mock_query_service):
    mock_query_service.retrieve_news.side_effect = Exception("Database error")

    response = client.get("/news")
    
    assert response.status_code == 500
    assert "Database error" in response.json()["detail"]
