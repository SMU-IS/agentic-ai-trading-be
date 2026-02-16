import asyncio
import json
from typing import AsyncGenerator, List

import aioredis
from src.config import settings
from src.models.state import TickerSentiment

class RedisService:
    def __init__(self):
        self.redis = None
        self.redis_news_stream = None
        self.redis_signal_stream = None
        self.redis_aggregator_stream = None
    
    async def connect(self):
        redis_con = f"redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}"
        self.redis = await aioredis.from_url(redis_con)

        self.redis_news_stream = settings.redis_news_stream
        self.redis_signal_stream = settings.redis_signal_stream
        self.redis_aggregator_stream = settings.redis_aggregator_stream

        print(f"✅ Redis: {redis_con}")
        print(f"📡 Listening to Aggregator Stream: '{self.redis_aggregator_stream}'")
        print(f"📤 Signal Stream: '{self.redis_signal_stream}'")
        print(f"📤 News Stream: '{self.redis_news_stream}'")
        
        # Test stream exists
        try:
            length = await self.redis.xlen(self.redis_aggregator_stream)
            print(f"📊 Stream length: {length}")
        except Exception as e:
            print(f"📭 ${e}")

    async def listen_news_stream(self) -> AsyncGenerator[TickerSentiment, None]:
        """✅ CORRECT aioredis xread syntax"""
        while True:
            try:
                messages = await self.redis.xread(
                block=1000,
                count=10,
                streams={self.redis_aggregator_stream: "0"}
            )
                
                if not messages:
                    continue

                for stream, msgs in messages:
                    for msg_id, fields in msgs:
                        decoded = {k.decode(): v.decode() for k, v in fields.items()}
                        print("📨 Ingesting News:", decoded)
                        tickers = self._extract_tickers_from_message(decoded)
                        print(f"   Extracted {tickers} tickers from message ID {msg_id}"   )
                        for ticker_sentiment in tickers:
                            yield ticker_sentiment

                        # Ack message
                        await self.redis.xdel(self.redis_aggregator_stream, msg_id)
                        
            except Exception as e:
                print(f"❌ Stream error: {e}")
                print(f"   Stream name: '{self.redis_aggregator_stream}'")
                await asyncio.sleep(1)

    def _extract_tickers_from_message(self, raw_data: dict) -> List[TickerSentiment]:
        tickers = []
    
        if isinstance(raw_data, dict) and len(raw_data) > 0:
            # Case 1: Multi-ticker format (tickers are keys)
            if any(key.isupper() and len(key) <= 5 for key in raw_data.keys()):  # heuristic for ticker symbols
                for ticker_symbol, sentiment_data in raw_data.items():
                    ticker_sentiment = TickerSentiment.from_dict(sentiment_data, ticker=ticker_symbol)
                    tickers.append(ticker_sentiment)
            # Case 2: Single-ticker stream format
            else:
                ticker_sentiment = TickerSentiment.from_stream_event(raw_data)
                tickers.append(ticker_sentiment)
        
        # Fallback: treat as single ticker dict
        if not tickers:
            ticker_sentiment = TickerSentiment.from_dict(raw_data)
            tickers.append(ticker_sentiment)
        
        return tickers
    
    async def publish_signal(self, signal: str):
        """Publish to trading agent queue"""
        await self.redis.xadd(self.redis_signal_stream, {"signal_id": signal})

    async def publish_news(self, signal: str):
        """Publish to trading agent queue"""
        await self.redis.xadd(self.redis_news_stream, {"signal_id": signal})
    
    async def track_volume(self, ticker_event: str) -> int:
        """Track volume for ticker:event_type combo"""
        key = f"volume:{ticker_event}"
        count = await self.redis.incr(key)
        await self.redis.expire(key, settings.hours_window * 3600)
        return count

    async def close(self):
        if self.redis:
            await self.redis.close()
