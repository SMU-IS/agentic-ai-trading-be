import json
import redis
import os
from core.config import env_config

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
