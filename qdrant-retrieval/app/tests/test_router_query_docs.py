import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock
from app.main import app
from app.services.query_qdrant import QueryQdrantService

client = TestClient(app)

@pytest.fixture
def mock_query_service():
    mock = MagicMock(spec=QueryQdrantService)
    mock.retrieve_ticker_insights = AsyncMock(return_value=[{"id": "1", "text": "test insight"}])
    
    app.dependency_overrides[QueryQdrantService] = lambda: mock
    yield mock
    app.dependency_overrides.clear()

def test_search_news_success(mock_query_service):
    payload = {
        "tickers": ["AAPL"],
        "query": "What is the latest news?",
        "limit": 5
    }
    

    response = client.post("/query", json=payload)
    
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["count"] == 1
    assert response.json()["results"][0]["text"] == "test insight"
    
    mock_query_service.retrieve_ticker_insights.assert_called_once()

def test_search_news_with_date_filtering(mock_query_service):
    payload = {
        "tickers": ["AAPL"],
        "query": "What happened on April 1st?",
        "limit": 5,
        "start_date": "2026-04-01T00:00:00",
        "end_date": "2026-04-01T23:59:59"
    }
    
    mock_query_service.retrieve_ticker_insights.return_value = [{"topic_id": "1", "text_content": "test insight"}]

    response = client.post("/query", json=payload)
    
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    
    mock_query_service.retrieve_ticker_insights.assert_called_once()
    actual_payload = mock_query_service.retrieve_ticker_insights.call_args[0][0]
    
    from datetime import datetime
    assert actual_payload.start_date == datetime.fromisoformat("2026-04-01T00:00:00")
    assert actual_payload.end_date == datetime.fromisoformat("2026-04-01T23:59:59")

def test_search_news_no_results(mock_query_service):
    mock_query_service.retrieve_ticker_insights.return_value = []
    
    payload = {
        "tickers": ["AAPL"],
        "query": "No news here",
        "limit": 5
    }
    
    response = client.post("/query", json=payload)
    
    assert response.status_code == 200
    assert response.json()["message"] == "No relevant documents found."
    assert response.json()["results"] == []

def test_search_news_error(mock_query_service):
    mock_query_service.retrieve_ticker_insights.side_effect = Exception("Search failed")
    
    payload = {
        "tickers": ["AAPL"],
        "query": "Error query",
        "limit": 5
    }
    
    response = client.post("/query", json=payload)
    
    assert response.status_code == 500
    assert "Search failed" in response.json()["detail"]
