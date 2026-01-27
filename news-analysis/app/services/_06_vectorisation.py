from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client.http import models

from app.core.security import get_current_user
from app.providers.vector.strategy import QdrantOllamaStrategy
from app.schemas.compiled_news_payload import NewsAnalysisPayload
from app.schemas.query_docs_payload import QueryDocsRequest

router = APIRouter(tags=["Ingest Documents"], dependencies=[Depends(get_current_user)])


class VectorisationService:
    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ):
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", " ", ""],
        )

        strategy = QdrantOllamaStrategy()
        self.vector_store = strategy.get_vector_store()

    async def ingest_docs(self, payload: NewsAnalysisPayload):
        """
        Saves payload to Qdrant.
        """

        try:
            vectors = f"{payload.metadata.headline}. {payload.metadata.text_content}"
            metadata = payload.metadata.model_dump()
            metadata["id"] = payload.id

            doc = Document(page_content=vectors, metadata=metadata)
            ids = await self.vector_store.aadd_documents(documents=[doc])
            print(f"✅ Saved document with id: {ids[0]}")  # type: ignore

            return {"status": "success", "id": ids[0]}  # type: ignore

        except Exception as e:
            # 5. Exception Handling
            print(f"❌ Error ingesting document: {str(e)}")

            raise RuntimeError(f"Failed to ingest document: {e}") from e

    async def query_docs(self, payload: QueryDocsRequest) -> List[Dict[str, Any]]:
        """
        Retrieves documents from Qdrant similar to the query.
        """

        search_filter = None
        if payload.ticker_filter:
            search_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="metadata.tickers",
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
                        "id": doc.metadata.get("id"),
                        "headline": doc.metadata.get("headline"),
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
