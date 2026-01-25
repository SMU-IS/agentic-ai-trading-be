import redis
from config import REDIS_HOST, REDIS_PORT, REDIS_STREAM_NAME


class RedisStreamStorage:
    def __init__(self, host=REDIS_HOST, port=REDIS_PORT, stream_name=REDIS_STREAM_NAME):
        self.r = redis.Redis(host=host, port=port, decode_responses=True)
        self.stream_name = stream_name

    def save(self, item: dict):
        self.r.xadd(self.stream_name, item)

    def save_batch(self, items: list[dict]):
        pipe = self.r.pipeline()
        for item in items:
            pipe.xadd(self.stream_name, item)
        pipe.execute()
