import json
import logging
from typing import Dict, Any, List, Optional, Tuple

import redis.asyncio as redis
from redis.exceptions import ResponseError

logger = logging.getLogger(__name__)


class RedisStreamStorage:
    def __init__(self, stream_name: str, redis_client: redis.Redis):
        """
        Redis client MUST be async and injected from outside.
        """
        self.r = redis_client
        self.stream_name = stream_name

    # ==========================================================
    # Basic Stream Operations
    # ==========================================================

    async def save(self, item: Dict[str, Any]) -> Optional[str]:
        """
        Save message to stream with built-in dedup (1-day TTL).
        Returns stream message ID if saved.
        Returns None if duplicate detected.
        """

        # ----------------------------------------
        # Extract unique ID for dedup
        # ----------------------------------------
        try:
            post_id = item.get('id')
        except KeyError:
            logger.error("❌ post id missing — cannot deduplicate")
            return None

        dedup_key = f"sentiment_dedup:{post_id}"

        # ----------------------------------------
        # Try acquiring dedup lock
        # ----------------------------------------
        acquired = await self.r.set(
            dedup_key,
            "1",
            nx=True,
            ex=60 * 60 * 24,  # 1 day
        )

        if not acquired:
            logger.info(f"⚠ Duplicate detected for {post_id} — skipping save")
            return None

        # ----------------------------------------
        # Save to stream
        # ----------------------------------------
        json_data = {k: json.dumps(v) for k, v in item.items()}
        msg_id = await self.r.xadd(self.stream_name, json_data)

        logger.info(f"✅ Saved stream message {msg_id} for {post_id}")

        return msg_id


    async def save_batch(self, items: List[Dict[str, Any]]) -> List[str]:
        """Save multiple messages using pipeline."""
        pipe = self.r.pipeline()
        for item in items:
            json_data = {k: json.dumps(v) for k, v in item.items()}
            pipe.xadd(self.stream_name, json_data)

        return await pipe.execute()

    async def read(
        self,
        last_id: str = "0-0",
        block_ms: int = 0,
        count: int = 10,
    ) -> List[tuple]:
        """Read stream without consumer group."""
        raw_entries = await self.r.xread(
            {self.stream_name: last_id},
            block=block_ms,
            count=count,
        )
        return self._deserialize_entries(raw_entries)

    # ==========================================================
    # Consumer Group Operations
    # ==========================================================

    async def create_consumer_group(
        self,
        group_name: str,
        start_id: str = "0",
        mkstream: bool = True,
    ) -> bool:
        """Create consumer group if not exists."""
        try:
            await self.r.xgroup_create(
                name=self.stream_name,
                groupname=group_name,
                id=start_id,
                mkstream=mkstream,
            )
            logger.info(
                f"Created consumer group '{group_name}' for '{self.stream_name}'"
            )
            return True

        except ResponseError as e:
            if "BUSYGROUP" in str(e):
                logger.debug(f"Group '{group_name}' already exists")
                return False
            raise

    async def read_group(
        self,
        group_name: str,
        consumer_name: str,
        count: int = 10,
        block_ms: int = 0,
        pending: bool = False,
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Read messages from consumer group.
        """
        read_id = ">" if not pending else "0"

        try:
            raw_entries = await self.r.xreadgroup(
                group_name,
                consumer_name,
                {self.stream_name: read_id},
                count=count,
                block=block_ms,
            )

        except ResponseError as e:
            if "NOGROUP" in str(e):
                logger.warning(f"Group {group_name} missing — recreating")
                await self.create_consumer_group(group_name, start_id="0")

                raw_entries = await self.r.xreadgroup(
                    group_name,
                    consumer_name,
                    {self.stream_name: read_id},
                    count=count,
                    block=block_ms,
                )
            else:
                raise

        results = []
        for _, messages in raw_entries:
            for msg_id, data in messages:
                results.append((msg_id, self._deserialize_dict(data)))

        return results

    async def acknowledge(self, group_name: str, *msg_ids: str) -> int:
        """Acknowledge processed messages."""
        if not msg_ids:
            return 0
        return await self.r.xack(self.stream_name, group_name, *msg_ids)

    async def get_pending(
        self,
        group_name: str,
        count: int = 10,
        consumer_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get pending messages."""
        try:
            if consumer_name:
                pending = await self.r.xpending_range(
                    self.stream_name,
                    group_name,
                    "-",
                    "+",
                    count,
                    consumername=consumer_name,
                )
            else:
                pending = await self.r.xpending_range(
                    self.stream_name,
                    group_name,
                    "-",
                    "+",
                    count,
                )

            return pending

        except ResponseError:
            return []

    async def claim_pending(
        self,
        group_name: str,
        consumer_name: str,
        min_idle_time_ms: int = 5000,
        count: int = 10,
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Claim idle pending messages from other consumers.
        """

        pending = await self.get_pending(group_name, count)

        print(f"🔎 Pending before claim: {pending}")

        if not pending:
            return []

        msg_ids = [
            entry["message_id"]
            for entry in pending
            if entry.get("time_since_delivered", 0) >= min_idle_time_ms
        ][:count]

        print(f"🔎 Claiming IDs: {msg_ids}")

        if not msg_ids:
            return []

        claimed = await self.r.xclaim(
            self.stream_name,
            group_name,
            consumer_name,
            min_idle_time_ms,
            msg_ids,
        )

        results = []
        for msg_id, data in claimed:
            if data:
                results.append(
                    (msg_id, self._deserialize_dict(data))
                )

        return results

    async def get_group_info(self, group_name: str) -> Optional[Dict]:
        """Return consumer group info."""
        try:
            groups = await self.r.xinfo_groups(self.stream_name)
            for group in groups:
                if group.get("name") == group_name:
                    return group
            return None
        except ResponseError:
            return None

    async def get_stream_length(self) -> int:
        """Get stream length."""
        try:
            return await self.r.xlen(self.stream_name)
        except ResponseError:
            return 0

    # ==========================================================
    # Maintenance
    # ==========================================================

    async def clear_stream(self):
        await self.r.delete(self.stream_name)

    async def delete_consumer_group(self, group_name: str) -> bool:
        try:
            await self.r.xgroup_destroy(self.stream_name, group_name)
            logger.info(f"Deleted group '{group_name}'")
            return True
        except ResponseError:
            return False

    async def delete(self, *msg_ids: str) -> int:
        """Delete messages from stream."""
        if not msg_ids:
            return 0

        try:
            deleted = await self.r.xdel(self.stream_name, *msg_ids)
            logger.info(
                f"Deleted {deleted} messages from '{self.stream_name}'"
            )
            return deleted

        except Exception as e:
            logger.error(f"Failed to delete {msg_ids}: {e}")
            return 0

    # ==========================================================
    # Helpers
    # ==========================================================

    def _deserialize_dict(self, data: Dict[str, str]) -> Dict[str, Any]:
        """
        Safely deserialize Redis stream values.
        Avoid crash if value is not valid JSON.
        """
        result = {}
        for k, v in data.items():
            try:
                result[k] = json.loads(v)
            except Exception:
                # If not JSON, return raw value
                result[k] = v
        return result

    def _deserialize_entries(self, raw_entries: List) -> List[tuple]:
        deserialized = []

        for stream_name, messages in raw_entries:
            msgs = []
            for msg_id, data in messages:
                msgs.append((msg_id, self._deserialize_dict(data)))
            deserialized.append((stream_name, msgs))

        return deserialized