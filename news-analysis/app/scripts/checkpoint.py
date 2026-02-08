# app/storage/redis_checkpoint.py
import redis
from app.core.config import env_config

class RedisCheckpoint:
    """
    Simple checkpoint stored in Redis as a key-value pair.
    Keeps track of the last processed ID for stream
    """

    def __init__(self, checkpoint_name: str, redis_client=None):
        self.r = redis_client or redis.Redis(host=env_config.redis_host, port=env_config.redis_port, password=env_config.redis_password, decode_responses=True)
        self.checkpoint_name = checkpoint_name
        self.key = f"checkpoint:{self.checkpoint_name}"

    def load(self) -> str:
        """
        Load the last processed ID from Redis.
        If not found, returns "0-0" (start of the stream)
        """
        last_id = self.r.get(self.key)
        return last_id if last_id else "0-0"

    def save(self, last_id: str):
        """
        Save the last processed ID to Redis.
        """
        self.r.set(self.key, last_id)
