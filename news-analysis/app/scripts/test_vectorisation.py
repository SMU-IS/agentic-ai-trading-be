import asyncio

from app.schemas.raw_news_payload import RedditSourcePayload
from app.services._06_vectorisation import VectorisationService

SAMPLE_QDRANT_RESULT = {
    "page_content": "AVAV down over 15% today. AVAV.....",
    "metadata": {
        "topic_id": "reddit:1qigodm",
        "tickers": ["AVAV", "AAPL"],
        "tickers_metadata": {
            "TSLA": {
                "event_type": "Earnings Report",
                "sentiment_score": 0.852341,
                "sentiment_label": "positive",
            },
            "ELON": {
                "event_type": "Earnings Report",
                "sentiment_score": -0.451234,
                "sentiment_label": "negative",
            },
            "timestamp": "2026-01-25T09:30:00Z",
            "source_domain": "bloomberg.com",
            "credibility_score": 0.95,
            "headline": "Tesla Q4 Earnings Beat Expectations",
            "text_content": "Tesla reported revenue of... [chunked text]...",
            "url": "https://bloomberg.com/news/...",
            "author": "Mark Gurman",
        },
    },
}

reddit_source_payload = {
    "id": "1770583212835-0",
    "fields": {
        "id": "reddit:1qigodm",
        "content_type": "post",
        "native_id": "1qigodm",
        "source": "reddit_batch",
        "author": "whereiskin",
        "url": "https://www.reddit.com/r/stocks/comments/1qigodm/avav_down_over_15_today/",
        "timestamps": "2026-01-20T23:04:33+00:00",
        "content": {
            "title": "AVAV down over 15% today",
            "body": 'AVAV\n\n“This morning, the U.S. Government "issued a stop work order on the Company\'s Other Transaction Agreement for the delivery of BADGER phased array antenna systems to support the Satellite Communication Augmentation Resource ("SCAR") program”\n\nBought a few shares at the end of the day. Anyone else pick some up?',
            "clean_title": "AVAV down over 15% today",
            "clean_body": 'AVAV "This morning, the U.S. Government "issued a stop work order on the Company\'s Other Transaction Agreement for the delivery of BADGER phased array antenna systems to support the Satellite Communication Augmentation Resource ("SCAR") program" Bought a few shares at the end of the day. Anyone else pick some up?',
            "clean_combined_withurl": 'AVAV down over 15% today. AVAV "This morning, the U.S. Government "issued a stop work order on the Company\'s Other Transaction Agreement for the delivery of BADGER phased array antenna systems to support the Satellite Communication Augmentation Resource ("SCAR") program" Bought a few shares at the end of the day. Anyone else pick some up?',
            "clean_combined_withouturl": 'AVAV down over 15% today. AVAV "This morning, the U.S. Government "issued a stop work order on the Company\'s Other Transaction Agreement for the delivery of BADGER phased array antenna systems to support the Satellite Communication Augmentation Resource ("SCAR") program" Bought a few shares at the end of the day. Anyone else pick some up?',
        },
        "engagement": {"total_comments": 16, "score": 23, "upvote_ratio": 0.78},
        "metadata": {"subreddit": "stocks", "category": None},
        "images": [],
        "links": [],
        "ticker_metadata": {
            "AVAV": {
                "type": "stock",
                "official_name": "AeroVironment Inc",
                "name_identified": ["AVAV"],
                "event_type": "REGULATORY_APPROVAL",
                "event_description": "The U.S. Government issued a stop work order on the Company's Other Transaction Agreement for the delivery of BADGER phased array antenna systems to support the Satellite Communication Augmentation Resource (",
                "event_proposal": None,
                "sentiment_score": -0.85,
                "sentiment_label": "negative",
                "sentiment_confidence": 0.6145,
                "sentiment_reasoning": "The company received a 'stop work order' from the U.S. Government on a significant program, which is a major negative regulatory event, causing the stock to drop over 15%.",
            }
        },
    },
}


async def run_test():
    print("🚀 Vectorising...")
    try:
        payload = RedditSourcePayload(**reddit_source_payload)
        print("✅ Payload Validated")
    except Exception as e:
        print(f"❌ Payload Validation Failed: {e}")
        return

    try:
        service = VectorisationService()
    except Exception as e:
        print(f"Error: {e}")
        return

    try:
        result = await service.get_sanitised_news_payload(payload)  # type: ignore
        print("\n🎉 Test Success!")
        print(f"Response: {result}")
    except RuntimeError as e:
        print(f"\n❌ Test Failed during ingestion: {e}")


if __name__ == "__main__":
    asyncio.run(run_test())
