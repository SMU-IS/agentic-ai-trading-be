import asyncio
import uuid
from xmlrpc import client
import numpy as np
from datetime import datetime, timedelta
from qdrant_client import QdrantClient
from qdrant_client.models import (
    PointStruct, VectorParams, Distance, Filter, FieldCondition, MatchValue, MatchAny, NestedCondition, Nested
)

async def fill_qdrant_tickers():
    """Fill Qdrant with dummy data matching your exact structure"""
    
    client = QdrantClient("localhost", port=6333)
    collection_name = "news_tickers"
    
    # Create collection
    try:
        client.get_collection(collection_name)
        print(f"✅ Collection '{collection_name}' exists")
    except:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE)
        )
        print(f"✅ Created '{collection_name}'")
    
    # Dummy data matching your structure
    dummy_articles = [
        {
            "headline": "Tesla Q4 Earnings Beat Expectations",
            "tickers_metadata": {
                "TSLA": {"event_type": "Earnings Report", "sentiment_score": 0.85, "sentiment_label": "positive"},
                "ELON": {"event_type": "Earnings Report", "sentiment_score": -0.45, "sentiment_label": "negative"}
            },
            "text_content": "Tesla reported Q4 revenue of $25.17B, beating analyst expectations by 3%. Elon Musk highlighted AI and robotaxi progress.",
            "source_domain": "bloomberg.com"
        },
        {
            "headline": "Apple Supply Chain Recovery",
            "tickers_metadata": {
                "AAPL": {"event_type": "Supply Chain", "sentiment_score": 0.72, "sentiment_label": "positive"},
                "FOX": {"event_type": "Supply Chain", "sentiment_score": 0.65, "sentiment_label": "positive"}
            },
            "text_content": "Foxconn resumes full iPhone production after China lockdown delays. Apple supply chain back to normal.",
            "source_domain": "reuters.com"
        },
        {
            "headline": "AVAV Government Contract Stopped",
            "tickers_metadata": {
                "AVAV": {"event_type": "Regulatory Approval", "sentiment_score": -0.85, "sentiment_label": "negative"}
            },
            "text_content": "U.S. Government issued stop-work order on AeroVironment's BADGER program for satellite communications.",
            "source_domain": "wsj.com"
        }
    ]
    
    points = []
    for article in dummy_articles:
        for i in range(20):  # 20 chunks per article
            # Generate unique IDs
            point_id = str(uuid.uuid4())
            article_id = str(uuid.uuid4())
            
            # Your exact payload structure
            payload = {
                "id": point_id,
                "metadata": {
                    "article_id": article_id,
                    "tickers_metadata": article["tickers_metadata"],
                    "ticker": list(article["tickers_metadata"].keys())[0],
                    "timestamp": (datetime.now() - timedelta(hours=i)).isoformat(),
                    "source_domain": article["source_domain"],
                    "credibility_score": round(np.random.uniform(0.8, 0.99), 2),
                    "headline": article["headline"],
                    "text_content": article["text_content"][:1000] + f"... [chunk {i+1}]",
                    "url": f"https://{article['source_domain']}/article/{article_id}",
                    "author": np.random.choice(["Mark Gurman", "John Doe", "Jane Smith"])
                }
            }
            
            # Random 384-dim vector
            vector = np.random.rand(384).tolist()
            points.append(PointStruct(id=point_id, vector=vector, payload=payload))
    
    print(f"📦 Created {len(points)} points")
    
    # Bulk upload
    print("🚀 Uploading...")
    client.upsert(collection_name=collection_name, points=points, wait=True)
    print("✅ Upload complete!")
    
    # Test ticker lookup
    print("\n🔍 Testing lookups...")
    
    for ticker in ["TSLA", "AAPL", "AVAV"]:
        filter_ticker = Filter(
            must=[
                FieldCondition(
                    key="metadata.ticker",  # Simple flat field ✅
                    match=MatchValue(value=ticker.upper())
                )
            ]
        )
        results = client.scroll(
            collection_name=collection_name,
            scroll_filter=filter_ticker,
            limit=3
        )
        points, _ = results
        print(f"✅ {ticker}: {len(points)} docs found")
    
    await client.close()

if __name__ == "__main__":
    asyncio.run(fill_qdrant_tickers())