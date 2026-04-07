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

    # Mock Qdrant scroll results
    mock_record = MagicMock()
    mock_record.payload = {
        "page_content": "Latest news content",
        "metadata": {"topic_id": "topic_latest", "timestamp": "2026-04-04T12:00:00Z"},
    }

    service.vector_store.client.scroll.return_value = ([mock_record], "next_offset_id")

    # Test with limit=50, offset=None
    result = await service.retrieve_news(limit=50, offset=None, sort_by_recency=True)

    assert len(result["results"]) == 1
    assert result["results"][0]["topic_id"] == "topic_latest"
    assert result["next_offset"] == "next_offset_id"

    service.vector_store.client.scroll.assert_called_once()
    args, kwargs = service.vector_store.client.scroll.call_args
    assert kwargs["limit"] == 50
    assert kwargs["offset"] is None
    assert isinstance(kwargs["order_by"], models.OrderBy)


@pytest.mark.asyncio
async def test_retrieve_latest_news_error(mock_qdrant_strategy):
    service = QueryQdrantService()
    service.vector_store.client.scroll.side_effect = Exception(
        "Qdrant scroll error"
    )

    with pytest.raises(
        RuntimeError, match="Failed to scroll news documents: Qdrant scroll error"
    ):
        await service.retrieve_news()
