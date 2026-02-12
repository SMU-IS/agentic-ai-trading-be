from src.services.qdrant import QdrantManager
from qdrant_client.http.models import FieldCondition, Filter, MatchValue

async def lookup_qdrant(ticker_symbol: str, limit: int = 10):
    """
    Memory: Fetches historical context or news related to the ticker.
    """
    print(f"   [🔍 Qdrant] Searching for historical context on {ticker_symbol}...")

    qdrant_client = QdrantManager.get_client()

    query_filter = Filter(
        must=[
            FieldCondition(
                key="metadata.ticker",
                match=MatchValue(value=ticker_symbol.upper())
            )
        ]
    )

    # ✅ CRITICAL: Add await!
    results = await qdrant_client.scroll(  # ← AWAIT HERE
        collection_name="news_tickers",
        scroll_filter=query_filter,
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )

    # ✅ Now results is tuple (points, next_offset)
    points, next_offset = results
    print(f"   [🔍 Qdrant] Found {len(points)} points for {ticker_symbol}")

    payloads = [p.payload for p in points]
    return payloads

