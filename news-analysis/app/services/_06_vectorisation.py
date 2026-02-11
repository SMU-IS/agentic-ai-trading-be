import uuid
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends
from langchain_core.documents import Document
from qdrant_client.http import models

from app.core.security import get_current_user
from app.providers.vector.strategy import QdrantOllamaStrategy
from app.schemas.compiled_news_payload import NewsAnalysisPayload
from app.schemas.query_docs_payload import QueryDocsRequest
from app.schemas.raw_news_payload import RedditSourcePayload

router = APIRouter(tags=["Ingest Documents"], dependencies=[Depends(get_current_user)])


class VectorisationService:
    def __init__(
        self,
    ):
        strategy = QdrantOllamaStrategy()
        self.vector_store = strategy.get_vector_store()

    async def get_sanitised_news_payload(self, processed_source: RedditSourcePayload):
        fields = processed_source.fields
        content, ticker_data, engagement, timestamps, author = (
            fields.content,
            fields.ticker_metadata,
            fields.engagement,
            fields.timestamps,
            fields.author,
        )

        transformed_tickers = {}
        for ticker, data in ticker_data.items():
            transformed_tickers[ticker] = {
                "event_type": data.event_type,
                "sentiment_score": data.sentiment_score,
                "sentiment_label": data.sentiment_label,
            }

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
                "article_id": processed_source.id,
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

    async def query_docs(self, payload: QueryDocsRequest) -> list[dict[str, Any]]:
        """
        Retrieves documents from Qdrant similar to the query.
        """

        search_filter = None
        if payload.ticker_filter:
            search_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="metadata.tickers_metadata",
                        match=models.MatchAny(any=payload.ticker_filter),
                    )
                ]
            )

        try:
            results = await self.vector_store.asimilarity_search_with_score(
                query=payload.query, k=payload.limit, filter=search_filter
            )

            formatted_results = []
            for doc, score in results:
                formatted_results.append(
                    {
                        "id": doc.metadata.get("article_id"),
                        "headline": doc.metadata.get("headline"),
                        "text_content": doc.metadata.get("text_content"),
                        "similarity_score": score,
                        "content_preview": doc.page_content[:200],
                        "metadata": doc.metadata,
                    }
                )

            print(
                f"✅ Found {len(formatted_results)} documents for query: '{payload.query}'"
            )
            return formatted_results

        except Exception as e:
            print(f"❌ Error during retrieval: {str(e)}")
            raise RuntimeError(f"Failed to retrieve documents: {e}") from e
