import asyncio

from app.schemas.compiled_news_payload import NewsAnalysisPayload
from app.services._06_vectorisation import VectorisationService

dummy_payload_data = {
    "id": "uuid-v4-generated-id",
    "metadata": {
        "article_id": "uuid-v4-generated-id",
        "tickers": ["TSLA", "ELON"],
        "timestamp": "2026-01-25T09:30:00Z",
        "source_domain": "bloomberg.com",
        "event_type": "Earnings Report",
        "credibility_score": 0.95,
        "sentiment_score": 0.88,
        "sentiment_label": "Positive",
        "headline": "Tesla Q4 Earnings Beat Expectations",
        "text_content": "Tesla reported revenue of... [chunked text]...",
        "url": "https://bloomberg.com/news/...",
        "author": "Mark Gurman",
    },
}


async def run_test():
    print("🚀 Vectorising...")
    try:
        payload = NewsAnalysisPayload(**dummy_payload_data)
        print("✅ Payload Validated")
    except Exception as e:
        print(f"❌ Payload Validation Failed: {e}")
        return

    try:
        service = VectorisationService()
        print("✅ Service Initialized (Connected to Qdrant/Ollama)")
    except Exception as e:
        print(f"❌ Connection Failed. Are Qdrant/Ollama running? Error: {e}")
        return

    try:
        result = await service.ingest_docs(payload)
        print("\n🎉 Test Success!")
        print(f"Response: {result}")
    except RuntimeError as e:
        print(f"\n❌ Test Failed during ingestion: {e}")


if __name__ == "__main__":
    asyncio.run(run_test())
