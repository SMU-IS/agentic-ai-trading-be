from typing import List
from src.services.redis_service import RedisService
from src.config import settings
from collections import defaultdict, Counter
from src.models.news import TickerSentiment

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
        
        print(f"📊 Event counts: {dict(ticker_event_counts.most_common(5))}")
        
        # Check each sentiment
        for sentiment in sentiments:
            triggered_sentiment = False
            
            # 1. Extreme sentiment trigger (|score| >= threshold)
            if abs(sentiment.sentiment_score) >= settings.sentiment_threshold:
                print(f"🚨 EXTREME: {sentiment.ticker} {sentiment.event_type} ({sentiment.sentiment_score:.2f})")
                triggered.append(sentiment)
                continue
            
            # 2. Volume trigger (5+ same event_type for ticker in time window)
            key = f"{sentiment.ticker}:{sentiment.event_type}"
            volume = ticker_event_counts[key]
            
            if volume >= settings.volume_threshold:
                print(f"📈 VOLUME: {sentiment.ticker}:{sentiment.event_type} x{volume}")
                sentiment.volume = volume  # Add volume attribute
                triggered.append(sentiment)
        
        print(f"✅ {len(triggered)}/{len(sentiments)} triggered")
        return triggered
