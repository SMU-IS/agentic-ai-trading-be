from src.services.qdrant import QdrantManager
from qdrant_client.http.models import FieldCondition, Filter, MatchAny, PayloadField, PayloadSchemaType, MatchValue, Nested
from src.config import settings
from sentence_transformers import SentenceTransformer

def get_generic_ticker_filter(ticker_symbol: str) -> Filter:
    ticker_key = ticker_symbol.upper()
    ticker_path = "tickers"
    
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
    # query_filter = get_generic_ticker_filter("AVAV")
    model = SentenceTransformer("all-MiniLM-L6-v2")
        
    collection_name = settings.qdrant_news_collection

    # await qdrant_client.create_payload_index(
    #     collection_name=collection_name, 
    #     field_name="tickers",
    #     field_schema=PayloadSchemaType.KEYWORD,
    # )
        
    # ✅ CRITICAL: Add await!
    # results = await qdrant_client.scroll(  # ← AWAIT HERE
    #     collection_name=collection_name,
    #     scroll_filter=query_filter,
    #     limit=limit,
    #     with_payload=True,
    #     with_vectors=False,
    # )
    query_vector = model.encode(query_vector_str).tolist()
    results = await qdrant_client.search(
        collection_name=collection_name,
        query_vector=query_vector,
        limit=2
    )
    for hit in results:
        print(f"Score: {hit.score:.3f} | Text: {hit.payload['text']}")

    # ✅ Now results is tuple (points, next_offset)
    # points, next_offset = results
    # print(f"   [🔍 Qdrant] Found {len(points)} points for {ticker_symbol}")

    # payloads = [p.payload for p in points]
    return results


if __name__ == "__main__":
    import asyncio

    async def test():
        results = await lookup_qdrant("AVAV REGULATORY_APPROVAL", limit=5)
        for i, res in enumerate(results):
            print(f"Result {i+1}: {res}")

    asyncio.run(test())