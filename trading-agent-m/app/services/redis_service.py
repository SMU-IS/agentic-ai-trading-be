import asyncio
from typing import AsyncGenerator

import redis.asyncio as aioredis

from app.agents.state import Signal
from app.core.config import env_config as settings


class RedisService:
    def __init__(self):
        self.redis = None
        self.redis_news_stream = None
        self.redis_signal_stream = None
        self.redis_aggregator_stream = None

    async def connect(self):

        self.redis = await aioredis.from_url(redis_con)

        self.redis_signal_stream = settings.redis_signal_stream

        print(f"✅ Redis: {redis_con}")
        print(f"📡 Listening to Signal Stream: '{self.redis_signal_stream}'")

        # Test stream exists
        try:
            length = await self.redis.xlen(self.redis_signal_stream)
            print(f"📊 Stream length: {length}")
        except Exception as e:
            print(f"📭 ${e}")

    async def listen_signal_stream(self) -> AsyncGenerator[Signal, None]:
        """✅ Yields Signal instances from Redis stream"""
        while True:
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

                        # Yield Signal instance
                        yield Signal(signal_id=decoded["signal_id"])
                        await self.redis.xdel(self.redis_signal_stream, msg_id)

            except Exception as e:
                print(f"❌ Stream error: {e}")
                print(f"   Stream name: '{self.redis_signal_stream}'")
                await asyncio.sleep(1)

    async def close(self):
        if self.redis:
            await self.redis.close()
