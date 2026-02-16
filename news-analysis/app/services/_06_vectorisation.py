from urllib.parse import urlparse

from fastapi import APIRouter, Depends
from langchain_core.documents import Document
from qdrant_client import models

from app.core.security import get_current_user
from app.providers.vector.strategy import QdrantGeminiStrategy
from app.schemas.compiled_news_payload import NewsAnalysisPayload
from app.schemas.raw_news_payload import RedditSourcePayload

router = APIRouter(tags=["Ingest Documents"], dependencies=[Depends(get_current_user)])


class VectorisationService:
    def __init__(
        self,
    ):
        self.strategy = QdrantGeminiStrategy()
        self.vector_store = self.strategy.get_vector_store()

    async def _setup_indexing(
        self, field_name: str, collection_name="news_analysis_compiled"
    ):
        client = self.vector_store.client  # type: ignore
        client.create_payload_index(
            collection_name=collection_name,
            field_name=f"metadata.{field_name}",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )

    async def _ensure_indexes(self):
        """Idempotent: Checks and creates necessary indexes for efficient querying."""
        await self._setup_indexing(field_name="metadata.tickers")
        # await self._setup_indexing(field_name="metadata.market_events.ticker")
        # await self._setup_indexing(field_name="metadata.market_events.event_type")

    async def get_sanitised_news_payload(self, processed_source: RedditSourcePayload):
        fields = processed_source.fields
        topic_id, content, ticker_data, engagement, timestamps, author = (
            fields.id,
            fields.content,
            fields.ticker_metadata,
            fields.engagement,
            fields.timestamps,
            fields.author,
        )

        transformed_tickers = {}

        for ticker, data in ticker_data.items():
            if data.event_type or data.event_proposal:
                transformed_tickers[ticker] = {
                    "event_type": data.event_type
                    or (
                        data.event_proposal.proposed_event_name
                        if data.event_proposal
                        else None
                    ),
                    "sentiment_score": data.sentiment_score,
                    "sentiment_label": data.sentiment_label,
                }
            else:
                continue

        url = fields.url
        try:
            domain = urlparse(url).netloc
        except Exception as e:
            import logging

            logging.error(f"Error parsing URL: {e}")
            domain = "reddit.com"

        sanitised_news_payload = {
            "id": processed_source.id,
            "metadata": {
                "topic_id": topic_id,
                "tickers": list(transformed_tickers.keys()),
                "tickers_metadata": transformed_tickers,
                "timestamp": timestamps,
                "source_domain": domain,
                "credibility_score": engagement.upvote_ratio,
                "headline": content.clean_title,
                "text_content": content.clean_body,
                "url": url,
                "author": author,
            },
        }

        await self._ensure_indexes()

        vector = content.clean_combined_withouturl
        final_payload = NewsAnalysisPayload(**sanitised_news_payload)
        is_success = await self._save_vectorised_payload(vector, final_payload)
        return is_success

    async def _save_vectorised_payload(self, vector: str, payload: NewsAnalysisPayload):
        """
        Saves payload to Qdrant.
        """

        try:
            doc = Document(page_content=vector, metadata=payload.metadata.model_dump())
            ids = await self.vector_store.aadd_documents(documents=[doc])
            print(f"✅ Saved document with id: {ids[0]}")  # type: ignore
            return {"status": "success", "id": ids[0]}  # type: ignore

        except Exception as e:
            print(f"❌ Error ingesting document: {str(e)}")
            raise RuntimeError(f"Failed to ingest document: {e}") from e
