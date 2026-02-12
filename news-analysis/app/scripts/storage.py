import redis
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from app.core.config import env_config

logger = logging.getLogger(__name__)


class RedisStreamStorage:
    def __init__(self, stream_name: str, redis_client=None):
        self.r = redis_client or redis.Redis(
            host=env_config.redis_host,
            port=env_config.redis_port,
            password=env_config.redis_password,
            decode_responses=True
        )
        self.stream_name = stream_name

    def save(self, item: Dict[str, Any]) -> str:
        """
        Save a single message to the stream.
        Returns the message ID.
        """
        json_data = {k: json.dumps(v) for k, v in item.items()}
        return self.r.xadd(self.stream_name, json_data)

    def save_batch(self, items: List[Dict[str, Any]]) -> List[str]:
        """
        Save multiple messages to the stream in a pipeline.
        Returns list of message IDs.
        """
        pipe = self.r.pipeline()
        for item in items:
            json_data = {k: json.dumps(v) for k, v in item.items()}
            pipe.xadd(self.stream_name, json_data)
        return pipe.execute()

    def read(
        self,
        last_id: str = "0-0",
        block_ms: int = 0,
        count: int = 10,
    ) -> List[tuple]:
        """
        Read messages from the stream (simple read without consumer groups).
        Returns a list of tuples: [(stream_name, [(msg_id, data_dict), ...]), ...]
        JSON fields are deserialized automatically.
        """
        raw_entries = self.r.xread({self.stream_name: last_id}, block=block_ms, count=count)
        return self._deserialize_entries(raw_entries)

    # ========== Consumer Group Methods ==========

    def create_consumer_group(
        self,
        group_name: str,
        start_id: str = "$",
        mkstream: bool = True
    ) -> bool:
        """
        Create a consumer group for reliable message processing.

        Args:
            group_name: Name of the consumer group
            start_id: Starting message ID ("$" = new messages only, "0" = all messages)
            mkstream: Create stream if it doesn't exist

        Returns:
            True if created, False if already exists
        """
        try:
            self.r.xgroup_create(
                self.stream_name,
                group_name,
                id=start_id,
                mkstream=mkstream
            )
            logger.info(f"Created consumer group '{group_name}' for stream '{self.stream_name}'")
            return True
        except redis.ResponseError as e:
            if "BUSYGROUP" in str(e):
                logger.debug(f"Consumer group '{group_name}' already exists")
                return False
            raise

    def read_group(
        self,
        group_name: str,
        consumer_name: str,
        count: int = 10,
        block_ms: int = 0,
        pending: bool = False
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Read messages using consumer groups for reliable processing.

        Args:
            group_name: Consumer group name
            consumer_name: Unique consumer identifier
            count: Max messages to read
            block_ms: Blocking timeout (0 = non-blocking)
            pending: If True, read pending messages (">"); if False, read new ("0")

        Returns:
            List of (msg_id, data_dict) tuples
        """
        # ">" = only new messages, "0" = pending messages for this consumer
        read_id = ">" if not pending else "0"

        try:
            raw_entries = self.r.xreadgroup(
                group_name,
                consumer_name,
                {self.stream_name: read_id},
                count=count,
                block=block_ms
            )
        except redis.ResponseError as e:
            if "NOGROUP" in str(e):
                logger.warning(f"Consumer group '{group_name}' not found, creating...")
                self.create_consumer_group(group_name, start_id="0")
                raw_entries = self.r.xreadgroup(
                    group_name,
                    consumer_name,
                    {self.stream_name: read_id},
                    count=count,
                    block=block_ms
                )
            else:
                raise

        # Flatten and deserialize
        results = []
        for stream_name, messages in raw_entries:
            for msg_id, data in messages:
                deserialized_data = {k: json.loads(v) for k, v in data.items()}
                results.append((msg_id, deserialized_data))

        return results

    def acknowledge(self, group_name: str, *msg_ids: str) -> int:
        """
        Acknowledge messages as processed.

        Args:
            group_name: Consumer group name
            msg_ids: Message IDs to acknowledge

        Returns:
            Number of messages acknowledged
        """
        if not msg_ids:
            return 0
        return self.r.xack(self.stream_name, group_name, *msg_ids)

    def get_pending(
        self,
        group_name: str,
        count: int = 10,
        consumer_name: Optional[str] = None
    ) -> List[Dict]:
        """
        Get pending messages (delivered but not acknowledged).

        Args:
            group_name: Consumer group name
            count: Max messages to return
            consumer_name: Filter by consumer (optional)

        Returns:
            List of pending message info dicts
        """
        try:
            if consumer_name:
                pending = self.r.xpending_range(
                    self.stream_name,
                    group_name,
                    "-",
                    "+",
                    count,
                    consumername=consumer_name
                )
            else:
                pending = self.r.xpending_range(
                    self.stream_name,
                    group_name,
                    "-",
                    "+",
                    count
                )
            return pending
        except redis.ResponseError:
            return []

    def claim_pending(
        self,
        group_name: str,
        consumer_name: str,
        min_idle_time_ms: int = 60000,
        count: int = 10
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Claim idle pending messages from other consumers.
        Useful for recovering from crashed consumers.

        Args:
            group_name: Consumer group name
            consumer_name: Consumer claiming the messages
            min_idle_time_ms: Minimum idle time to claim (default 60s)
            count: Max messages to claim

        Returns:
            List of (msg_id, data_dict) tuples
        """
        try:
            # Get pending messages
            pending = self.get_pending(group_name, count)
            if not pending:
                return []

            # Filter by idle time and claim
            msg_ids = [
                p['message_id'] for p in pending
                if p.get('time_since_delivered', 0) >= min_idle_time_ms
            ]

            if not msg_ids:
                return []

            claimed = self.r.xclaim(
                self.stream_name,
                group_name,
                consumer_name,
                min_idle_time_ms,
                msg_ids
            )

            # Deserialize
            results = []
            for msg_id, data in claimed:
                if data:  # Can be None if message was deleted
                    deserialized_data = {k: json.loads(v) for k, v in data.items()}
                    results.append((msg_id, deserialized_data))

            return results
        except redis.ResponseError as e:
            logger.error(f"Failed to claim pending messages: {e}")
            return []

    def get_group_info(self, group_name: str) -> Optional[Dict]:
        """
        Get consumer group info including pending count and consumers.
        """
        try:
            groups = self.r.xinfo_groups(self.stream_name)
            for group in groups:
                if group.get('name') == group_name:
                    return group
            return None
        except redis.ResponseError:
            return None

    def get_stream_length(self) -> int:
        """Get the number of messages in the stream."""
        try:
            return self.r.xlen(self.stream_name)
        except redis.ResponseError:
            return 0

    # ========== Helper Methods ==========

    def _deserialize_entries(self, raw_entries: List) -> List[tuple]:
        """Deserialize raw Redis stream entries."""
        deserialized = []
        for stream_name, messages in raw_entries:
            deserialized_messages = []
            for msg_id, data in messages:
                deserialized_data = {k: json.loads(v) for k, v in data.items()}
                deserialized_messages.append((msg_id, deserialized_data))
            deserialized.append((stream_name, deserialized_messages))
        return deserialized

    def clear_stream(self):
        """Delete stream for testing purposes."""
        self.r.delete(self.stream_name)

    def delete_consumer_group(self, group_name: str) -> bool:
        """Delete a consumer group."""
        try:
            self.r.xgroup_destroy(self.stream_name, group_name)
            logger.info(f"Deleted consumer group '{group_name}'")
            return True
        except redis.ResponseError:
            return False

    def delete(self, *msg_ids: str) -> int:
        """
        Delete one or more messages from the stream by ID.

        Args:
            msg_ids: One or more Redis Stream message IDs to delete

        Returns:
            Number of messages deleted
        """
        if not msg_ids:
            return 0
        try:
            deleted_count = self.r.xdel(self.stream_name, *msg_ids)
            logger.info(f"Deleted {deleted_count} message(s) from stream '{self.stream_name}'")
            return deleted_count
        except redis.RedisError as e:
            logger.error(f"Failed to delete messages {msg_ids} from stream '{self.stream_name}': {e}")
            return 0
