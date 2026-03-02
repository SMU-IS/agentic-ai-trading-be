from typing import List
from src.services.redis_service import RedisService
from src.config import settings
from collections import defaultdict, Counter
from src.models.state import TickerSentiment

class ThresholdMonitor:
    def __init__(self, redis: RedisService):
        self.redis = redis
    
    async def check_triggers(self, sentiments: List[TickerSentiment]) -> List[TickerSentiment]:
        """Check sentiment and event volume triggers"""
        triggered = []
        
        # Group by ticker + event_type
        ticker_event_counts = Counter()
        ticker_sentiments = defaultdict(list)
        
        for sentiment in sentiments:
            key = f"{sentiment.ticker}:{sentiment.event_type}"
            ticker_event_counts[key] += 1
            ticker_sentiments[sentiment.ticker].append(sentiment)
        
        # print(f"📊 Event counts: {dict(ticker_event_counts.most_common(5))}")
        
        # Check each sentiment
        for sentiment in sentiments:
            # Checks if topic was digested previously
            ticker_event = f"{sentiment.ticker}:{sentiment.event_type}"
            if await self.redis.is_digested(ticker_event):
                continue
            
            # 1. Extreme sentiment trigger (|score| >= threshold)
            if abs(sentiment.sentiment_score) >= settings.sentiment_threshold:
                print(f"🚨 EXTREME: {sentiment.ticker} {sentiment.event_type} ({sentiment.sentiment_score:.2f})")
                triggered.append(sentiment)
                await self.redis.mark_digested(ticker_event)
                continue
            
            # 2. Volume trigger (using Redis persistent tracking)
            volume = await self.redis.track_volume(ticker_event)  # ✅ Uses Redis tracking
            print(f"📊Count for event: {ticker_event} at {volume}")

            if volume >= settings.volume_threshold:
                print(f"📈 VOLUME: {ticker_event} x{volume}")
                sentiment.volume = volume  # Add volume attribute
                triggered.append(sentiment)
                await self.redis.mark_digested(ticker_event)
        
        print(f"✅ {len(triggered)}/{len(sentiments)} triggered")
        return triggered
