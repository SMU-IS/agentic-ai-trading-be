from app.core.config import env_config
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.http import models


class VectorStore:
    def __init__(self):
        self.embeddings = OpenAIEmbeddings(
            model=env_config.text_embedding_model,
            base_url=env_config.ollama_base_url,
            api_key=env_config.open_ai_api_key,  # type: ignore
            tiktoken_enabled=False,
            check_embedding_ctx_length=False,
            chunk_size=16,
        )

        self.client = QdrantClient(url=env_config.qdrant_url)
        self.collection_name = "agentic_ai_trading_docs"

        if not self.client.collection_exists(self.collection_name):
            print(f"Creating collection: {self.collection_name}")

            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=1024,
                    distance=models.Distance.COSINE,
                ),
            )

    def get_store(self) -> QdrantVectorStore:
        """
        Returns a LangChain compatible VectorStore object.
        """

        return QdrantVectorStore(
            client=self.client,
            collection_name=self.collection_name,
            embedding=self.embeddings,
        )


vector_store = VectorStore()
