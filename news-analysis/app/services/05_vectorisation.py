from typing import List

from app.core.security import get_current_user
from fastapi import APIRouter, Depends
from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter

router = APIRouter(tags=["Ingest Documents"], dependencies=[Depends(get_current_user)])


class VectorisationService:
    def __init__(
        self,
        vector_store: VectorStore,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ):
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", " ", ""],
        )
        self.vector_store = vector_store

    async def ingest_docs(self, raw_docs: List[Document]):
        """
        Loads, splits, and saves documents to Qdrant.
        """

        split_docs = self.text_splitter.split_documents(raw_docs)
        await self.vector_store.aadd_documents(split_docs)

        return {"status": "success", "chunks_ingested": len(split_docs)}
