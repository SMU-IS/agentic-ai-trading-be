from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from qdrant_client import models

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
async def test_retrieve_news_success(mock_qdrant_strategy):
    service = QueryQdrantService()

    # Mock Qdrant query_points results
    mock_point = MagicMock()
    mock_point.payload = {
        "page_content": "Latest news content",
        "metadata": {"topic_id": "topic_latest", "timestamp": "2026-04-04T12:00:00Z"},
    }

    mock_response = MagicMock()
    mock_response.points = [mock_point]
    service.vector_store.client.query_points.return_value = mock_response

    # Test with limit=50, offset=0
    result = await service.retrieve_news(limit=50, offset=0, sort_by_recency=True)

    assert len(result["results"]) == 1
    assert result["results"][0]["topic_id"] == "topic_latest"
    assert result["next_offset"] is None  # Since only 1 result was returned for a limit of 50

    service.vector_store.client.query_points.assert_called_once()
    args, kwargs = service.vector_store.client.query_points.call_args
    assert kwargs["limit"] == 50
    assert kwargs["offset"] == 0
    assert isinstance(kwargs["query"], dict)
    assert kwargs["query"]["order_by"]["key"] == "metadata.timestamp"
    assert kwargs["query"]["order_by"]["direction"] == "desc"


@pytest.mark.asyncio
async def test_retrieve_latest_news_error(mock_qdrant_strategy):
    service = QueryQdrantService()
    service.vector_store.client.query_points.side_effect = Exception(
        "Qdrant query error"
    )

    with pytest.raises(
        RuntimeError, match="Failed to query news documents: Qdrant query error"
    ):
        await service.retrieve_news()
