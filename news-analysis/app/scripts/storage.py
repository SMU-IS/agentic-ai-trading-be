import redis
import json
from typing import Dict, Any, List
from app.core.config import env_config


class RedisStreamStorage:
    def __init__(self, stream_name: str, redis_client=None):
        self.r = redis_client or redis.Redis(host=env_config.redis_host, port=env_config.redis_port, password=env_config.redis_password, decode_responses=True)
        self.stream_name = stream_name

    def save(self, item: Dict[str, Any]):
        """
        Save a single message to the stream.
        """
        json_data = {k: json.dumps(v) for k, v in item.items()}
        self.r.xadd(self.stream_name, json_data)

    def save_batch(self, items: List[Dict[str, Any]]):
        """
        Save multiple messages to the stream in a pipeline.
        """
        pipe = self.r.pipeline()
        for item in items:
            json_data = {k: json.dumps(v) for k, v in item.items()}
            pipe.xadd(self.stream_name, json_data)
        pipe.execute()

    def read(
        self,
        last_id: str = "0-0",
        block_ms: int = 0,
        count: int = 10,
    ) -> List[tuple]:
        """
        Read messages from the stream.
        Returns a list of tuples: [(stream_name, [(msg_id, data_dict), ...]), ...]
        JSON fields are deserialized automatically.
        """
        raw_entries = self.r.xread({self.stream_name: last_id}, block=block_ms, count=count)
        deserialized = []

        for stream_name, messages in raw_entries:
            deserialized_messages = []
            for msg_id, data in messages:
                # Deserialize JSON values
                deserialized_data = {k: json.loads(v) for k, v in data.items()}
                deserialized_messages.append((msg_id, deserialized_data))
            deserialized.append((stream_name, deserialized_messages))

        return deserialized
    
    # delete stream for testing purposes
    def clear_stream(self):
        self.r.delete(self.stream_name)
