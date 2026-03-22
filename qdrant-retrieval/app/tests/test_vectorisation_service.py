import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.vectorisation import VectorisationService
from app.schemas.raw_news_payload import RedditSourcePayload
from app.data.mock_reddit_payload import MOCK_REDDIT_PAYLOAD

@pytest.fixture
def mock_strategy():
    with patch("app.services.vectorisation.get_vector_strategy") as mock:
        strategy_instance = MagicMock()
        mock.return_value = strategy_instance
        vector_store = MagicMock()
        vector_store.aadd_documents = AsyncMock(return_value=["test-id"])
        strategy_instance.get_vector_store.return_value = vector_store
        yield strategy_instance

@pytest.mark.asyncio
async def test_get_sanitised_news_payload(mock_strategy):
    service = VectorisationService()
    
    payload = RedditSourcePayload(**MOCK_REDDIT_PAYLOAD)
    
    result = await service.get_sanitised_news_payload(payload)
    
    assert result["status"] == "success"
    assert result["id"] == "test-id"
    
    service.vector_store.aadd_documents.assert_called_once()
    
    call_args = service.vector_store.aadd_documents.call_args
    docs = call_args.kwargs["documents"]
    assert len(docs) == 1
    doc = docs[0]
    
    assert doc.page_content == payload.fields.content.clean_combined_withouturl
    assert doc.metadata["topic_id"] == payload.fields.id
    assert "AVAV" in doc.metadata["tickers"]
    assert doc.metadata["source_domain"] == "www.reddit.com"
    assert doc.metadata["credibility_score"] == payload.fields.engagement.upvote_ratio

@pytest.mark.asyncio
async def test_ensure_indexes(mock_strategy):
    service = VectorisationService()
    
    mock_client = MagicMock()
    service.vector_store.client = mock_client
    
    await service.ensure_indexes()
    
    assert mock_client.create_payload_index.call_count == 3
    
    mock_client.create_payload_index.assert_any_call(
        collection_name="news_analysis_compiled",
        field_name="tickers",
        field_schema=pytest.importorskip("qdrant_client.models").PayloadSchemaType.KEYWORD
    )

@pytest.mark.asyncio
async def test_get_sanitised_news_payload_error(mock_strategy):
    service = VectorisationService()
    service.vector_store.aadd_documents.side_effect = Exception("Ingestion failed")
    
    payload = RedditSourcePayload(**MOCK_REDDIT_PAYLOAD)
    
    with pytest.raises(RuntimeError, match="Failed to ingest document: Ingestion failed"):
        await service.get_sanitised_news_payload(payload)
