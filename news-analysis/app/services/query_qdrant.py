from typing import Any

from fastapi import APIRouter, Depends
from qdrant_client import models

from app.core.security import get_current_user
from app.providers.vector.strategy import QdrantGeminiStrategy
from app.schemas.query_docs_payload import QueryDocsRequest

router = APIRouter(
    tags=["Query Qdrant Documents"], dependencies=[Depends(get_current_user)]
)


class QueryQdrant:
    def __init__(self):
        self.strategy = QdrantGeminiStrategy()
        self.vector_store = self.strategy.get_vector_store()

    async def retrieve_ticker_insights(
        self, payload: QueryDocsRequest
    ) -> list[dict[str, Any]]:
        """
        Performs a semantic similarity search to identify and retrieve relevant context.

        Args:
            payload (QueryDocsRequest): An object containing:
                - query (str): The search text.
                - limit (int): Max number of results.
                - tickers (list[str]): List of tickers to filter by.

        Returns:
            list[dict[str, Any]]: List of documents with metadata and similarity score.
        """

        filter_by_tickers = models.Filter(
            must=[
                models.FieldCondition(
                    key="metadata.tickers",
                    match=models.MatchAny(any=payload.tickers),
                )
            ]
        )

        try:
            results = await self.vector_store.asimilarity_search_with_score(
                query=payload.query, k=payload.limit, filter=filter_by_tickers
            )

            formatted_results = []
            for doc, score in results:
                formatted_results.append(
                    {
                        "topic_id": doc.metadata.get("topic_id"),
                        "text_content": doc.metadata.get("text_content"),
                        "similarity_score": score,
                    }
                )

            print(
                f"✅ Found {len(formatted_results)} documents for query: '{payload.query}'"
            )
            return formatted_results

        except Exception as e:
            print(f"❌ Error during retrieval: {str(e)}")
            raise RuntimeError(f"Failed to retrieve documents: {e}") from e

    # def _build_ticker_event_filter(self, ticker: str, event_type: str) -> models.Filter:
    #     return models.Filter(
    #         must=[
    #             models.NestedCondition(
    #                 path="metadata.market_events",
    #                 filter=models.Filter(
    #                     must=[
    #                         models.FieldCondition(
    #                             key="ticker", match=models.MatchValue(value=ticker)
    #                         ),
    #                         models.FieldCondition(
    #                             key="event_type",
    #                             match=models.MatchValue(value=event_type),
    #                         ),
    #                     ]
    #                 ),
    #             )
    #         ]
    #     )

    # async def retrieved_filtered_ticker_events(
    #     self, ticker: str, event_type: str
    # ) -> list[dict[str, Any]]:
    #     condition = self._build_ticker_event_filter(ticker, event_type)
    #     try:
    #         results = await self.vector_store.client.scroll(
    #             collection_name="news_analysis_compiled",
    #             query_vector=None,
    #             limit=10,
    #             scroll_filter=condition,
    #             with_payload=True,
    #             with_vectors=False,
    #         )

    #         formatted_results = []
    #         for res in results:
    #             doc = res.payload
    #             formatted_results.append(
    #                 {
    #                     "topic_id": doc.payload.get("metadata", {}).get("topic_id"),
    #                     "text_content": doc.payload.get("page_content"),
    #                     "event_details": {
    #                         "ticker": ticker,
    #                         "event_type": event_type,
    #                     },
    #                 }
    #             )

    #         print(
    #             f"✅ Found {len(formatted_results)} documents for ticker: '{ticker}' and event type: '{event_type}'"
    #         )
    #         return formatted_results

    #     except Exception as e:
    #         print(f"❌ Error during filtered retrieval: {str(e)}")
    #         raise RuntimeError(f"Failed to retrieve filtered documents: {e}") from e
