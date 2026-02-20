from app.core.constant import StorageProviders
from app.providers.vector.strategy import QdrantGeminiStrategy, QdrantOllamaStrategy

VECTOR_STRATEGIES = {
    StorageProviders.QDRANT_OLLAMA: QdrantOllamaStrategy(),
    StorageProviders.QDRANT_GEMINI: QdrantGeminiStrategy(),
}


def get_vector_strategy(provider: StorageProviders):
    strategy = VECTOR_STRATEGIES.get(provider)
    if not strategy:
        raise ValueError(f"Unsupported provider: {provider}")

    return strategy
