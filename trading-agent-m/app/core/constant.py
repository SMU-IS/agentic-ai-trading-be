from enum import Enum


class LLMProviders(str, Enum):
    OLLAMA = "ollama"


class StorageProviders(str, Enum):
    QDRANT_OLLAMA = "qdrant_ollama"
