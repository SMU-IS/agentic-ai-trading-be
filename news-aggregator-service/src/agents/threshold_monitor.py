from typing import List
from src.models.news import TickerTopic
from src.services.redis_service import RedisService
from src.config import settings

class ThresholdMonitor:
    def __init__(self, redis: RedisService):
        self.redis = redis
    
    async def check_triggers(self, topics: List[TickerTopic]) -> List[TickerTopic]:
        triggered = []
        
        for topic in topics:
            key = f"{topic.ticker}:{topic.topic}"
            
            # Sentiment trigger
            if abs(topic.sentiment) >= settings.sentiment_threshold:
                triggered.append(topic)
                continue
            
            # Volume trigger
            volume = await self.redis.track_volume(key)
            topic.volume = volume
            
            if volume >= settings.volume_threshold:
                triggered.append(topic)
        
        return triggered
