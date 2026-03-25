from typing import Type
from app.core.constant import StorageProviders
from app.providers.vector.strategy import VectorStorageStrategy, QdrantGeminiStrategy, QdrantOllamaStrategy, QdrantNomicStrategy

VECTOR_STRATEGIES: dict[StorageProviders, Type[VectorStorageStrategy]] = {
    StorageProviders.QDRANT_OLLAMA: QdrantOllamaStrategy,
    StorageProviders.QDRANT_GEMINI: QdrantGeminiStrategy,
    StorageProviders.QDRANT_NOMIC: QdrantNomicStrategy,
}


def get_vector_strategy(provider: StorageProviders) -> VectorStorageStrategy:
    strategy_class = VECTOR_STRATEGIES.get(provider)
    if not strategy_class:
        raise ValueError(f"Unsupported provider: {provider}")

    return strategy_class()
