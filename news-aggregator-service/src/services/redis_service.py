import asyncio
import json
import aioredis
from typing import AsyncGenerator, List
from src.config import settings
from src.models.news import TickerSentiment

class RedisService:
    def __init__(self):
        self.redis = None
    
    async def connect(self):
        self.redis = await aioredis.from_url(settings.redis_url)
        print(f"✅ Redis: {settings.redis_url}")
        print(f"📡 Stream: '{settings.news_stream}'")  # Should print 'news:sentiment'
        print(f"📤 Queue: '{settings.signal_queue}'")
        
        # Test stream exists
        try:
            length = await self.redis.xlen(settings.news_stream)
            print(f"📊 Stream length: {length}")
        except:
            print("📭 Stream empty (normal)")
    
    async def listen_news_stream(self) -> AsyncGenerator[TickerSentiment, None]:
        """✅ CORRECT aioredis xread syntax"""
        while True:
            try:
                messages = await self.redis.xread(
                block=1000,
                count=10,
                streams={settings.news_stream: "0"}
            )
                
                if not messages:
                    continue
                    
                for stream, msgs in messages:
                    for msg_id, fields in msgs:

                        raw_data_str = fields[b"data"].decode('utf-8')
                        raw_data = json.loads(raw_data_str)
                        print("📨 Fields:", raw_data)
                        tickers = self._extract_tickers_from_message(raw_data)
                        print(f"   Extracted {tickers} tickers from message ID {msg_id}"   )
                        for ticker_sentiment in tickers:
                            yield ticker_sentiment
                        
                        # Ack message
                        await self.redis.xdel(settings.news_stream, msg_id)
                        
            except Exception as e:
                print(f"❌ Stream error: {e}")
                print(f"   Stream name: '{settings.news_stream}'")
                await asyncio.sleep(1)

    def _extract_tickers_from_message(self, raw_data: dict) -> List[TickerSentiment]:
        tickers = []
        if isinstance(raw_data, dict) and len(raw_data) > 0:
            for ticker_symbol, sentiment_data in raw_data.items():
                ticker_sentiment = TickerSentiment.from_dict(sentiment_data, ticker=ticker_symbol)
                tickers.append(ticker_sentiment)
        return tickers or [TickerSentiment.from_dict(raw_data)]
    
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
