import asyncio
import json
from datetime import datetime
from src.services.redis_service import RedisService
from src.models.news import NewsArticle

async def publish_test_news():
    redis = RedisService()
    await redis.connect()
    
    # Sample news for testing
    test_articles = {
        "AVAV":{
            "Type": "stock",
            "OfficialName": "AeroVironment Inc",
            "NameIdentified": ["AVAV"],
            "event_type": "REGULATORY_APPROVAL",
            "event_description": "The U.S. Government issued a stop work order...",
            "event_proposal": None,
            "sentiment_score": -0.85,
            "sentiment_label": "negative",
            "sentiment_confidence": 0.6145,
            "sentiment_reasoning": "The company received a 'stop work order'..."
        }
    }
    
    print("📤 Publishing test news to news:sentiment...")

    await redis.redis.xadd("news:sentiment", {"data": json.dumps(test_articles)})
    print("✅ Published test news article.")
    await asyncio.sleep(1)  # 1s between articles
    
    await redis.close()

if __name__ == "__main__":
    asyncio.run(publish_test_news())