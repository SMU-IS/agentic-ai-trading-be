from abc import ABC, abstractmethod

from app.core.config import env_config
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import VectorStore as LangChainVectorStore
from langchain_ollama import OllamaEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.http import models


class VectorStorageStrategy(ABC):
    @abstractmethod
    def get_embeddings(self) -> Embeddings:
        pass

    @abstractmethod
    def get_vector_store(self) -> LangChainVectorStore:
        pass


# Strategy A: Qdrant + Ollama
class QdrantOllamaStrategy(VectorStorageStrategy):
    def __init__(self):
        self.client = QdrantClient(
            url=env_config.qdrant_url, api_key=env_config.qdrant_api_key
        )
        self.collection_name = "news_analysis_compiled"

        self._ensure_collection_exists()

    def get_embeddings(self) -> Embeddings:
        return OllamaEmbeddings(
            model=env_config.text_embedding_model, base_url=env_config.ollama_base_url
        )

    def get_vector_store(self) -> LangChainVectorStore:
        return QdrantVectorStore(
            client=self.client,
            collection_name=self.collection_name,
            embedding=self.get_embeddings(),
        )

    def _ensure_collection_exists(self):
        """
        Check if the collection exists on the Qdrant server.
        If not, create it with the correct vector dimensions.
        """

        if not self.client.collection_exists(collection_name=self.collection_name):
            print(f"🚀 Creating new collection: {self.collection_name}")
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=1024, distance=models.Distance.COSINE
                ),
            )
        else:
            print(f"✅ Collection '{self.collection_name}' already exists.")


# Strategy B: Chroma + OpenAI (Future Cloud setup)
# class ChromaOpenAIStrategy(VectorStorageStrategy): ...
