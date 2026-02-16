from src.services.qdrant import QdrantManager
from qdrant_client.http.models import FieldCondition, Filter, MatchValue
from src.config import settings
from typing import List

def get_generic_ticker_filter(ticker_symbol: str) -> Filter:
    ticker_key = ticker_symbol.upper()
    ticker_path = "metadata.tickers"
    
    print(f"   [🔍 Qdrant] Creating filter for ticker {ticker_key} at path {ticker_path}")
    
    return Filter(
        must=[
            FieldCondition(
                key=ticker_path,
                match=MatchValue(value=ticker_key)  # ← correct: any= takes a list
            )
        ]
    )

    
async def lookup_qdrant(query_vector_str: str, limit: int = 10):
    """
    Memory: Fetches historical context or news related to the ticker.
    """
    # print(f"   [🔍 Qdrant] Searching for historical context on {ticker_symbol}...")

    qdrant_client = QdrantManager.get_client()
    query_filter = get_generic_ticker_filter("AVAV")
        
    collection_name = settings.qdrant_news_collection
        
    # ✅ CRITICAL: Add await!
    results = await qdrant_client.scroll(  # ← AWAIT HERE
        collection_name=collection_name,
        scroll_filter=query_filter,
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )
    # ✅ Now results is tuple (points, next_offset)
    points, next_offset = results
    payloads = [p.payload for p in points]
    print(payloads)
    return payloads


if __name__ == "__main__":
    import asyncio

    async def test():
        results = await lookup_qdrant("AVAV REGULATORY_APPROVAL", limit=5)
        for i, res in enumerate(results):
            print(f"Result {i+1}: {res}")

    asyncio.run(test())