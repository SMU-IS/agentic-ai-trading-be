from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.security import get_current_user
from app.providers.vector.strategy import QdrantOllamaStrategy
from app.schemas.compiled_news_payload import NewsAnalysisPayload

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

    async def query_docs(
        self, query: str, limit: int = 3, score_threshold: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        Retrieves documents from Qdrant similar to the query.
        """

        try:
            results = await self.vector_store.asimilarity_search_with_score(
                query=query, k=limit, score_threshold=score_threshold
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

            print(f"✅ Found {len(formatted_results)} documents for query: '{query}'")
            return formatted_results

        except Exception as e:
            print(f"❌ Error during retrieval: {str(e)}")
            raise RuntimeError(f"Failed to retrieve documents: {e}") from e
