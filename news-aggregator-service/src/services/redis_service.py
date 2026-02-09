import asyncio
import json
import aioredis
from typing import AsyncGenerator
from src.config import settings
from src.models.news import NewsArticle

class RedisService:
    def __init__(self):
        self.redis = None
    
    async def connect(self):
        self.redis = await aioredis.from_url(settings.redis_url)
    
    async def listen_news_stream(self) -> AsyncGenerator[NewsArticle, None]:
        """Continuously listen to news stream"""
        while True:
            try:
                messages = await self.redis.xread(
                    [{settings.news_stream: "$"}],
                    block=1000,
                    count=10
                )
                for stream, msgs in messages:
                    for msg_id, fields in msgs:
                        data = json.loads(fields[b"data"])
                        article = NewsArticle(**data)
                        yield article
                        await self.redis.xdel(settings.news_stream, msg_id)
            except Exception as e:
                print(f"Stream error: {e}")
                await asyncio.sleep(1)
    
    async def publish_signal(self, signal: dict):
        """Publish to trading agent queue"""
        await self.redis.xadd(settings.signal_queue, {"signal": json.dumps(signal)})
    
    async def track_volume(self, ticker_topic: str) -> int:
        """Track article volume per ticker+topic"""
        key = f"volume:{ticker_topic}"
        count = await self.redis.incr(key)
        await self.redis.expire(key, settings.hours_window * 3600)
        return count
    
    async def close(self):
        if self.redis:
            await self.redis.close()
