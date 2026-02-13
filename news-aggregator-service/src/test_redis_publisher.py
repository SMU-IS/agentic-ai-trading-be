import asyncio
import json
from src.services.redis_service import RedisService

async def publish_test_news():
    redis = RedisService()
    await redis.connect()
    
    # Sample news for testing
    # test_articles = {
    #     "AVAV": {
    #         "Type": "stock",
    #         "OfficialName": "AeroVironment Inc",
    #         "NameIdentified": [
    #             "AVAV"
    #         ],
    #         "event_type": "REGULATORY_APPROVAL",
    #         "event_description": "The U.S. Government issued a stop work order on the Company's Other Transaction Agreement for the delivery of BADGER phased array antenna systems to support the Satellite Communication Augmentation Resource (",
    #         "event_proposal": None,
    #         "sentiment_score": -0.85,
    #         "sentiment_label": "negative",
    #         "sentiment_confidence": 0.6145,
    #         "sentiment_reasoning": "The company received a 'stop work order' from the U.S. Government on a significant program, which is a major negative regulatory event, causing the stock to drop over 15%."
    #     }
    # }
    
    test_articles = {
        "stream_event_type": "NEWS_UPDATE",
        "id": "reddit:1r2a9xx",
        "ticker": "NFLX",
        "ticker_event_type": "EARNINGS_BEAT",
        "sentiment_score": 0.92,  # 🔥 HIGH SENTIMENT
        "sentiment_confidence": 0.9142,
        "event_description": "Netflix Q4 2026 earnings CRUSH expectations: +22M subscribers, $11.8B revenue, 35% ad-tier growth, NFLX shares +12% after-hours",
        "sentiment_reasoning": "Netflix delivered monster Q4 results with record subscriber growth (22M vs 15M expected), revenue beat ($11.8B vs $11.2B), and advertising revenue exploding 35% YoY. Management raised 2027 guidance, announced $18B buyback, and confirmed live sports expansion (NFL games, boxing PPVs). Analysts upgrading targets to $1600+. Clear BUY signal with massive momentum."
    }

    # test_articles = {
    #     "stream_event_type": "NEWS_UPDATE",
    #     "id": "reddit:1r0tftt",
    #     "ticker": "IBRX",
    #     "ticker_event_type": "REGULATORY_APPROVAL",
    #     "sentiment_score": 0.85,
    #     "sentiment_confidence": 0.6145,
    #     "event_description": "Saudi SFDA approval for ANKTIVA in NMIBC CIS",
    #     "sentiment_reasoning": "The article highlights a significant price surge for IBRX driven by positive regulatory news (Saudi SFDA approval) and promising clinical trial developments, indicating strong bullish sentiment."
    # }
    

    print("📤 Publishing test news to news:sentiment...")

    await redis.redis.xadd("news_notification_stream", {"data": json.dumps(test_articles)})
    print("✅ Published test news article.")
    await asyncio.sleep(1)  # 1s between articles
    
    await redis.close()

if __name__ == "__main__":
    asyncio.run(publish_test_news())