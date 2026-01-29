import asyncio

from app.schemas.event_models import (
    NewsPayload,
)
from app.services._03_event_identification import EventIdentifierService


async def main():
    raw_json = {
        "Post_ID": "t3_raw001",
        "Post_URL": "https://www.reddit.com/r/stocks/comments/raw001/",
        "Author": "marketwatcher92",
        "Timestamp_UTC": 1704067200,
        "Timestamp_ISO": "2024-01-01T00:00:00",
        "Total_Comments": 245,
        "Score": 1820,
        "Upvote_Ratio": 0.93,
        "Subreddit": "stocks",
        "Domain": "reddit.com",
        "urls": ["https://www.cnbc.com/2024/01/10/apple-earnings"],
        "images": [],
        "raw_title": "Apple reports strong Q4 earnings &amp; beats expectations 🚀",
        "raw_body": "Apple Inc. ($AAPL) just reported earnings.\n\nFull article here: ...",
        "clean_title": "Apple reports strong Q4 earnings & beats expectations 🚀",
        "clean_body": "Apple Inc. ($AAPL) just reported earnings. Full article here: ...",
        "clean_combined": "Apple reports strong Q4 earnings & beats expectations 🚀. Apple Inc. ($AAPL) just reported earnings.",
    }

    print("--- ✏️  1. Test Case A: spaCy-based ---")
    payload = NewsPayload(**raw_json)
    print(f"✅ Mapped Headline: {payload.headline}")
    print(f"✅ Mapped Content:  {payload.content[:50]}...")

    service = EventIdentifierService()
    result = await service.process_event(payload)

    print("\n🎯 Event Detected: True")
    print(f"🛠️  Method: {result.method}")
    print(f"📝 Summary: {result.summary}")

    dummy_llm_payload = {
        "clean_title": "Market Panic",
        "clean_body": "Tech stocks plummeted heavily during the morning session due to fears of inflation.",
        "clean_combined": "",
    }

    print("\n--- 🧠 2. Test Case B: LLM Augmented ---")
    p2 = NewsPayload(
        **dummy_llm_payload,
    )
    r2 = await service.process_event(p2)
    print("\n🎯 Event Detected: True")
    print(f"🛠️  Method: {r2.method}")
    print(f"📝 Summary: {r2.summary}")


if __name__ == "__main__":
    asyncio.run(main())
