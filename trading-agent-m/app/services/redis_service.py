import asyncio
from typing import AsyncGenerator, Dict

import redis.asyncio as aioredis

from app.agents.state import Signal
from app.core.config import env_config as settings

# Redis timestamp
from datetime import datetime
from zoneinfo import ZoneInfo

class RedisService:
    def __init__(self):
        self.redis = None
        self.redis_signal_stream = None
        self.redis_trade_noti_stream = None
        
    async def connect(self):
        redis_con = f"redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}"
        self.redis = await aioredis.from_url(redis_con)

        self.redis_signal_stream = settings.redis_signal_stream
        self.redis_trade_noti_stream = settings.redis_trading_noti_stream
        
        print(f"✅ Redis: {redis_con}")
        print(f"📡 Listening to Signal Stream: '{self.redis_signal_stream}'")

        # Test stream exists
        try:
            length = await self.redis.xlen(self.redis_signal_stream)
            print(f"📊 Stream length: {length}")
        except Exception as e:
            print(f"📭 ${e}")

    async def listen_signal_stream(self, enabled_event: asyncio.Event) -> AsyncGenerator[Signal, None]:
        """✅ Yields Signal instances from Redis stream. Stops reading when enabled_event is cleared."""
        while True:
            if not enabled_event.is_set():
                await asyncio.sleep(1)
                continue

            try:
                messages = await self.redis.xread(
                    block=1000, count=10, streams={self.redis_signal_stream: "0"}
                )

                if not messages:
                    continue

                for stream, msgs in messages:
                    for msg_id, fields in msgs:
                        decoded = {k.decode(): v.decode() for k, v in fields.items()}
                        print("📨 Ingesting Signal:", decoded)

                        yield Signal(signal_id=decoded["signal_id"])
                        await self.redis.xdel(self.redis_signal_stream, msg_id)

            except Exception as e:
                print(f"❌ Stream error: {e}")
                print(f"   Stream name: '{self.redis_signal_stream}'")
                await asyncio.sleep(1)
                
    async def publish_trade_noti(self, noti_order_id: list[Dict]):
        """Publish to trading notification stream"""
        for noti in noti_order_id:
            order_id = noti.get("order_id")
            user_id  = noti.get("user_id")
            await self.redis.xadd(self.redis_trade_noti_stream, {"order_id": order_id, "user_id": user_id})
            print(f"   [📢 Redis] Trade notification published | user={user_id} order={order_id}")
        
    async def publish_order_timestamp(self, post_id, ticker):

        POST_TIMESTAMP = "post_timestamps"
        sg_now = datetime.now(ZoneInfo("Asia/Singapore")).isoformat()

        await self.redis.hset(
                f"{POST_TIMESTAMP}:{post_id}",
                f"order_timestamp:{ticker}",
                sg_now
            )
        
    async def pipeline_counter(self):
        agent_pipeline_key = "pipeline:agent"
        await self.redis.incr(agent_pipeline_key)
        
    async def get_service_enabled(self) -> bool:
        """Read services:trading-agent-m -> enabled field — returns True if missing (default on)"""
        val = await self.redis.hget(settings.redis_service_control_key, "enabled")
        if val is None:
            return True
        return val.decode().lower() in ("1", "true", "yes")

    async def close(self):
        if self.redis:
            await self.redis.close()

async def test():
    redis_service = RedisService()
    await redis_service.connect()
    await redis_service.publish_order_timestamp("reddit:1qwymfr", "PLTR")
    
if __name__ == "__main__":
    import asyncio
    asyncio.run(test())