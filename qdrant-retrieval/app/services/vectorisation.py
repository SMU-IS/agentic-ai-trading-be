from urllib.parse import urlparse
import uuid

from langchain_core.documents import Document
from qdrant_client import models
from app.core.config import env_config
from app.core.constant import StorageProviders
from app.providers.vector.registry import get_vector_strategy
from app.core.logger import logger
from app.schemas.compiled_news_payload import NewsAnalysisPayload
from app.schemas.raw_news_payload import SourcePayload


class VectorisationService:
    def __init__(
        self,
    ):
        self.strategy = get_vector_strategy(
            StorageProviders(env_config.storage_provider)
        )
        self.vector_store = self.strategy.get_vector_store()

    async def _setup_indexing(
        self, field_name: str, collection_name="news_analysis_compiled"
    ):
        try:
            client = self.vector_store.client
            client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
        except Exception as e:
            logger.warning(f"Index on {field_name} may already exist: {e}")

    async def ensure_indexes(self):
        """
        Idempotent: Checks and creates necessary indexes for efficient querying.
        """

        await self._setup_indexing(field_name="metadata.tickers")
        await self._setup_indexing(field_name="metadata.tickers_metadata[].ticker")
        await self._setup_indexing(field_name="metadata.tickers_metadata[].event_type")

    async def get_sanitised_news_payload(self, processed_source: SourcePayload):
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

        transformed_tickers_flat = [
            {
                "ticker": ticker,
                "event_type": data["event_type"],
                "sentiment_score": data["sentiment_score"],
                "sentiment_label": data["sentiment_label"],
            }
            for ticker, data in transformed_tickers.items()
        ]

        url = fields.url
        try:
            domain = urlparse(url).netloc
        except Exception as e:
            logger.error(f"Error parsing URL: {e}")
            domain = "unknown"

        credibility_score = engagement.upvote_ratio if engagement.upvote_ratio is not None else 0.5

        sanitised_news_payload = {
            "id": processed_source.id,
            "metadata": {
                "topic_id": topic_id,
                "tickers": list(transformed_tickers.keys()),
                "tickers_metadata": transformed_tickers_flat,
                "timestamp": timestamps,
                "source_domain": domain,
                "credibility_score": credibility_score,
                "headline": content.clean_title,
                "text_content": content.clean_body,
                "url": url,
                "author": author,
            },
        }

        vector = content.clean_combined_withouturl
        final_payload = NewsAnalysisPayload(**sanitised_news_payload)
        is_success = await self._save_vectorised_payload(vector, final_payload)
        return is_success

    def _string_to_uuid(self, value: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, value))

    async def _save_vectorised_payload(self, vector: str, payload: NewsAnalysisPayload):
        """
        Saves payload to Qdrant.
        """

        try:
            post_id = payload.metadata.topic_id
            post_id_uuid = self._string_to_uuid(post_id)
            doc = Document(page_content=vector, metadata=payload.metadata.model_dump(), id=post_id_uuid)
            ids = await self.vector_store.aadd_documents(documents=[doc])
            logger.info(f"✅ Saved document with id: {ids[0]}")  # type: ignore
            return {"status": "success", "id": ids[0]}  # type: ignore

        except Exception as e:
            logger.error(f"❌ Error ingesting document: {str(e)}")
            raise RuntimeError(f"Failed to ingest document: {e}") from e
