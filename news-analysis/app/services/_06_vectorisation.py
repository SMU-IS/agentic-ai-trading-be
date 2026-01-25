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
