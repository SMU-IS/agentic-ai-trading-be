from typing import Any

from qdrant_client import models

from app.core.logger import logger
from app.providers.vector.strategy import QdrantNomicStrategy
from app.schemas.query_docs_payload import QueryDocsRequest


class QueryQdrantService:
    def __init__(self):
        self.strategy = (
            QdrantNomicStrategy()
        )  # TODO: Make this dynamic based on config/env
        self.vector_store = self.strategy.get_vector_store()

    async def retrieve_all_news(
        self, limit: int = 20, offset: Any = None
    ) -> dict[str, Any]:
        """
        Retrieves a page of documents from the collection without any filters.

        Args:
            limit (int): Number of documents to return.
            offset (Any): The ID from which to start scrolling (for pagination).

        Returns:
            dict: A dictionary containing the list of documents and the next offset.
        """
        try:
            records, next_offset = self.vector_store.client.scroll(
                collection_name="news_analysis_compiled",
                limit=limit,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )

            formatted_results = []
            for record in records:
                payload = record.payload
                metadata = payload.get("metadata", {})
                formatted_results.append(
                    {
                        "topic_id": metadata.get("topic_id"),
                        "text_content": payload.get("page_content")
                        or metadata.get("text_content"),
                        "metadata": metadata,
                    }
                )
            return {"results": formatted_results, "next_offset": next_offset}

        except Exception as e:
            logger.error(f"❌ Error retrieving all news: {str(e)}")
            raise RuntimeError(f"Failed to scroll documents: {e}")

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

    def _build_ticker_event_filter(self, ticker: str, event_type: str) -> models.Filter:
        return models.Filter(
            must=[
                models.FieldCondition(
                    key="metadata.tickers_metadata[].ticker",
                    match=models.MatchValue(value=ticker.upper()),
                ),
                models.FieldCondition(
                    key="metadata.tickers_metadata[].event_type",
                    match=models.MatchValue(value=event_type.upper()),
                ),
            ]
        )

    def retrieved_filtered_ticker_events(
        self, ticker: str, event_type: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Retrieve ticker events with fallback to ticker-only search if not enough results."""

        exact_results = self._scroll_by_ticker_and_event_type(ticker, event_type, limit)
        formatted_results = self._format_results(exact_results, ticker, event_type)

        if len(formatted_results) < limit:
            remaining_count = limit - len(formatted_results)
            fallback_results = self._scroll_by_ticker_only(
                ticker,
                remaining_count,
                seen_topic_ids={r["topic_id"] for r in formatted_results},
            )

            formatted_fallback = self._format_results(
                fallback_results, ticker, event_type
            )
            formatted_results.extend(formatted_fallback)

        logger.info(
            f"✅ Found {len(formatted_results)} documents for ticker: '{ticker}' and event type: '{event_type}'"
        )
        return formatted_results

    def _scroll_by_ticker_and_event_type(
        self, ticker: str, event_type: str, limit: int
    ) -> list:
        """Scroll Qdrant with both ticker and event type filter."""

        condition = self._build_ticker_event_filter(ticker, event_type)
        results, _ = self.vector_store.client.scroll(
            collection_name="news_analysis_compiled",
            scroll_filter=condition,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return results

    def _scroll_by_ticker_only(
        self, ticker: str, limit: int, seen_topic_ids: set
    ) -> list:
        """Scroll Qdrant with ticker filter only, excluding seen topic_ids."""

        condition = models.Filter(
            must=[
                models.FieldCondition(
                    key="metadata.tickers_metadata[].ticker",
                    match=models.MatchValue(value=ticker.upper()),
                ),
            ]
        )
        results, _ = self.vector_store.client.scroll(
            collection_name="news_analysis_compiled",
            scroll_filter=condition,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )

        return [
            r
            for r in results
            if r.payload.get("metadata", {}).get("topic_id") not in seen_topic_ids
        ]

    def _format_results(
        self, results: list, ticker: str, event_type: str
    ) -> list[dict[str, Any]]:
        """Format raw Qdrant results into the response structure."""

        formatted = []
        for result in results:
            payload = result.payload
            formatted.append(
                {
                    "topic_id": payload.get("metadata", {}).get("topic_id"),
                    "text_content": payload.get("page_content"),
                    "event_details": {
                        "ticker": ticker,
                        "event_type": event_type,
                    },
                }
            )
        return formatted
