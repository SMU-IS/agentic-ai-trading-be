import pytest
from unittest.mock import MagicMock, patch
from app.services.query_qdrant import QueryQdrantService

@pytest.fixture
def mock_qdrant_strategy():
    with patch("app.services.query_qdrant.get_vector_strategy") as mock:
        strategy_instance = MagicMock()
        mock.return_value = strategy_instance
        vector_store = MagicMock()
        strategy_instance.get_vector_store.return_value = vector_store
        yield strategy_instance

@pytest.mark.asyncio
async def test_retrieve_all_news_success(mock_qdrant_strategy):
    service = QueryQdrantService()
    
    # Mock Qdrant scroll results
    mock_record = MagicMock()
    mock_record.payload = {
        "page_content": "Article content",
        "metadata": {
            "topic_id": "topic_1",
            "text_content": "Article content",
            "source": "Bloomberg"
        }
    }
    
    service.vector_store.client.scroll.return_value = ([mock_record], "next_offset_123")
    
    result = await service.retrieve_all_news(limit=10, offset=None)
    
    assert "results" in result
    assert "next_offset" in result
    assert result["next_offset"] == "next_offset_123"
    assert len(result["results"]) == 1
    assert result["results"][0]["topic_id"] == "topic_1"
    assert result["results"][0]["text_content"] == "Article content"
    
    service.vector_store.client.scroll.assert_called_once_with(
        collection_name="news_analysis_compiled",
        limit=10,
        offset=None,
        with_payload=True,
        with_vectors=False
    )

@pytest.mark.asyncio
async def test_retrieve_all_news_empty(mock_qdrant_strategy):
    service = QueryQdrantService()
    
    service.vector_store.client.scroll.return_value = ([], None)
    
    result = await service.retrieve_all_news(limit=20)
    
    assert result["results"] == []
    assert result["next_offset"] is None

@pytest.mark.asyncio
async def test_retrieve_all_news_error(mock_qdrant_strategy):
    service = QueryQdrantService()
    service.vector_store.client.scroll.side_effect = Exception("Qdrant error")
    
    with pytest.raises(RuntimeError, match="Failed to scroll documents: Qdrant error"):
        await service.retrieve_all_news()
