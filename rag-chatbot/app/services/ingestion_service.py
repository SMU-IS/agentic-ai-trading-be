from typing import List

from bs4.filter import SoupStrainer
from langchain_community.document_loaders import WebBaseLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.vector_store import vector_store


class IngestionService:
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", " ", ""],
        )
        self.vector_store = vector_store.get_store()

    def _load_web_content(self, urls: List[str]) -> List[Document]:
        """
        Loads and parses specific content from web pages.
        """

        bs4_strainer = SoupStrainer(
            class_=("post-title", "post-header", "post-content")
        )

        loader = WebBaseLoader(
            web_paths=urls,
            bs_kwargs={"parse_only": bs4_strainer},
        )

        return loader.load()

    async def ingest_docs(self, urls: List[str]):
        """
        Loads, splits, and saves documents to Qdrant.
        """

        raw_docs = self._load_web_content(urls)
        split_docs = self.text_splitter.split_documents(raw_docs)
        self.vector_store.add_documents(split_docs)

        return {"status": "success", "chunks_ingested": len(split_docs)}
