from app.core.config import env_config
from qdrant_client import AsyncQdrantClient


class QdrantManager:
    _instance = None

    @classmethod
    def get_client(cls):
        if cls._instance is None:
            url = env_config.qdrant_url
            cls._instance = AsyncQdrantClient(url=url, timeout=5)
            print(f"   [⚡ Qdrant] Connection initialized to {url}")
        return cls._instance

    @classmethod
    async def close_client(cls):
        if cls._instance:
            await cls._instance.close()
            cls._instance = None
