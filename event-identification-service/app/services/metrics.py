import time
import redis.asyncio as redis
from datetime import datetime
from zoneinfo import ZoneInfo

METRICS_TTL_SECONDS = 60 * 60 * 24  # 24 hours rolling window


class MetricsTracker:
    def __init__(self, redis_client: redis.Redis, service_name: str):
        self.redis = redis_client
        self.service_name = service_name

        # keys namespaced per service — no collisions across services
        self._received_key  = f"{service_name}:metrics:received"
        self._processed_key = f"{service_name}:metrics:processed"

    # ----------------------------------------------------------
    # RECORD
    # ----------------------------------------------------------
    async def record_received(self):
        """Get current time when reading post from prev stream"""
        now = time.time()
        pipe = self.redis.pipeline()
        pipe.zadd(self._received_key, {str(now): now})
        pipe.expire(self._received_key, METRICS_TTL_SECONDS)
        await pipe.execute()
        # remove entries older than 24 hours
        await self._trim(self._received_key)

    async def record_processed(self, latency_ms: float):
        """Call only when post makes past whole service processing"""
        now = time.time()
        # store as "timestamp:latency" so we can recover latency later
        member = f"{now}:{latency_ms:.2f}"
        pipe = self.redis.pipeline()
        pipe.zadd(self._processed_key, {member: now})
        pipe.expire(self._processed_key, METRICS_TTL_SECONDS)
        await pipe.execute()
        await self._trim(self._processed_key)

    # ----------------------------------------------------------
    # TRIM — remove entries older than 24hrs
    # ----------------------------------------------------------
    async def _trim(self, key: str):
        cutoff = time.time() - METRICS_TTL_SECONDS
        await self.redis.zremrangebyscore(key, "-inf", cutoff)

    # ----------------------------------------------------------
    # QUERY
    # ----------------------------------------------------------
    async def get_metrics(self, window_hours: int = 1) -> dict:
        now = time.time()
        cutoff = now - (window_hours * 3600)

        pipe = self.redis.pipeline()
        pipe.zcount(self._received_key, cutoff, "+inf")
        pipe.zrangebyscore(self._processed_key, cutoff, "+inf", withscores=True)
        results = await pipe.execute()

        received        = int(results[0])
        processed_entries = results[1]
        processed       = len(processed_entries)
        dropped         = received - processed

        # parse latency from member string
        latencies = []
        for member, _score in processed_entries:
            try:
                latencies.append(float(member.split(":")[1]))
            except (ValueError, IndexError):
                continue

        avg_latency_ms = round(sum(latencies) / len(latencies), 2) if latencies else None

        # last processed timestamp
        last_processed_at = None
        if processed_entries:
            last_ts = processed_entries[-1][1]
            last_processed_at = datetime.fromtimestamp(
                last_ts, tz=ZoneInfo("Asia/Singapore")
            ).isoformat()

        return {
            "service":           self.service_name,
            "window_hours":      window_hours,
            "received":          received,
            "processed":         processed,
            "dropped":           dropped,
            "avg_latency_ms":    avg_latency_ms,
            "last_processed_at": last_processed_at,
            "status":            "idle" if processed == 0 else "active",
        }

    async def get_metrics_all_windows(self) -> dict:
        """Return metrics for 1hr, 6hr, 24hr windows in one call."""
        one_hr = await self.get_metrics(window_hours=1)
        six_hr = await self.get_metrics(window_hours=6)
        day    = await self.get_metrics(window_hours=24)
        return {
            "1hr":  one_hr,
            "6hr":  six_hr,
            "24hr": day,
        }
