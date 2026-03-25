import json

import redis

from app.core.config import env_config


class RedisStreamStorage:
    def __init__(
        self,
        stream_name: str = env_config.redis_stream_name,
        host: str = env_config.redis_host,
        port: int = env_config.redis_port,
    ):
        self.r = redis.Redis(
            host=host,
            port=port,
            password=env_config.redis_password,
            decode_responses=True,
        )
        self.stream_name = stream_name

    def save(self, item: dict):
        data = json.dumps(item, ensure_ascii=False)
        self.r.xadd(self.stream_name, {"data": data})

    def save_batch(self, items: list[dict]):
        pipe = self.r.pipeline()
        for item in items:
            data = json.dumps(item, ensure_ascii=False)
            pipe.xadd(self.stream_name, {"data": data})
        pipe.execute()


def get_redis_client() -> redis.Redis:
    """Create and return a Redis client using config settings."""
    return redis.Redis(
        host=env_config.redis_host,
        port=env_config.redis_port,
        password=env_config.redis_password,
        decode_responses=True,
    )


def publish_to_stream(redis_client: redis.Redis, stream_name: str, item: dict):
    """Serialize item to JSON and publish to a Redis stream."""
    data = json.dumps(item, ensure_ascii=False)
    redis_client.xadd(stream_name, {"data": data})


def check_and_mark_seen(
    redis_client: redis.Redis, key: str, set_name: str, ttl_days: int = None
) -> bool:
    """
    Check if key has been seen before using a Redis key.
    Returns True if already seen (duplicate), False if new.
    Marks unseen keys permanently (no TTL) by default.
    Pass ttl_days to set an expiry.
    """
    redis_key = f"{set_name}:{key}"
    if redis_client.exists(redis_key):
        return True
    if ttl_days:
        redis_client.set(redis_key, 1, ex=ttl_days * 86400)
    else:
        redis_client.set(redis_key, 1)
    return False
