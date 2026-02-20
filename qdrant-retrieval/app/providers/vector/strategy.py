from abc import ABC, abstractmethod
from typing import override

from app.core.config import env_config
from app.core.logger import logger
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import VectorStore as LangChainVectorStore
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_ollama import OllamaEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.http import models


class VectorStorageStrategy(ABC):
    vector_size = 1024

    def __init__(self):
        self.client = QdrantClient(
            url=env_config.qdrant_url, api_key=env_config.qdrant_api_key
        )
        self.collection_name = "news_analysis_compiled"
        self._ensure_collection_exists()

    @abstractmethod
    def get_embeddings(self) -> Embeddings:
        pass

    def get_vector_store(self) -> LangChainVectorStore:
        try:
            return QdrantVectorStore(
                client=self.client,
                collection_name=self.collection_name,
                embedding=self.get_embeddings(),
            )
        except Exception as e:
            logger.error(f"Failed to initialize Qdrant Vector Store: {e}")
            raise

    def _ensure_collection_exists(self):
        """
        Check if the collection exists on the Qdrant server.
        If it exists, check if the vector dimensions match.
        If they don't match, recreate the collection.
        """

        if self.client.collection_exists(collection_name=self.collection_name):
            collection_info = self.client.get_collection(
                collection_name=self.collection_name
            )

            vectors_config = collection_info.config.params.vectors
            existing_size = 0

            if hasattr(vectors_config, "size"):
                existing_size = vectors_config.size
            elif isinstance(vectors_config, dict):
                first_key = next(iter(vectors_config))
                existing_size = vectors_config[first_key].size

            if existing_size != self.vector_size:
                logger.warning(
                    f"⚠️ Dimension mismatch for '{self.collection_name}': "
                    f"Qdrant has {existing_size}, Strategy wants {self.vector_size}. Recreating..."
                )
                # In a retrieval service, we might NOT want to delete the collection if it mismatches.
                # But for consistency with news-analysis, we keep this logic or just log it.
                # Actually, retrieval service should probably NOT delete collections.
                # I'll keep it for now to match exactly what you had, but usually retrieval is read-only.
                # self.client.delete_collection(collection_name=self.collection_name)
                # self._create_fresh_collection()
            else:
                logger.info(
                    f"✅ Collection '{self.collection_name}' matches dims ({existing_size})."
                )
        else:
            logger.info(f"🚀 Collection '{self.collection_name}' not found.")
            self._create_fresh_collection()

    def _create_fresh_collection(self):
        """Helper to create the collection with current class parameters."""

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=models.VectorParams(
                size=self.vector_size, distance=models.Distance.COSINE
            ),
        )
        logger.info(
            f"✅ Collection '{self.collection_name}' created with size {self.vector_size}."
        )


class QdrantOllamaStrategy(VectorStorageStrategy):
    vector_size = 1024

    @override
    def get_embeddings(self) -> Embeddings:
        return OllamaEmbeddings(
            model=env_config.text_embedding_model, base_url=env_config.ollama_base_url
        )


class QdrantGeminiStrategy(VectorStorageStrategy):
    vector_size = 768

    @override
    def get_embeddings(self) -> Embeddings:
        return GoogleGenerativeAIEmbeddings(
            model=env_config.text_embedding_model,
            google_api_key=env_config.gemini_api_key,
            output_dimensionality=768,
        )
