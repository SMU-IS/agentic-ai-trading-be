#!/usr/bin/env python3
# populate_qdrant_fixed.py
import uuid
import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)

DUMMY_EMBEDDING_SIZE = 10


def generate_dummy_embedding(size: int = DUMMY_EMBEDDING_SIZE) -> list[float]:
    return np.random.rand(size).tolist()


def main():
    client = QdrantClient(url="http://localhost:6333")
    collection_name = "historical_data"

    # 1. Create collection if it doesn't exist
    try:
        client.get_collection(collection_name)
        print(f"✅ Collection '{collection_name}' already exists.")
    except Exception:
        print(f"📦 Creating collection '{collection_name}'...")
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=DUMMY_EMBEDDING_SIZE, distance=Distance.COSINE),
        )
        print("✅ Collection created.")

    # 2. Generate dummy financial data for AAPL
    dummy_points = []
    for i in range(20):
        point = PointStruct(
            id=str(uuid.uuid4()),
            vector=generate_dummy_embedding(),
            payload={
                "ticker": "AAPL",
                "timestamp": f"2026-01-{10+i:02d}T12:00:00Z",
                "price": 150.0 + np.random.normal(0, 5),
                "sentiment": np.random.choice(["bullish", "bearish", "neutral"]),
                "news_headline": f"Dummy AAPL news #{i}: {'Strong earnings' if i % 3 == 0 else 'Market volatility'}",
                "volume": np.random.randint(1000000, 10000000),
            },
        )
        dummy_points.append(point)

    # 3. Upsert points
    client.upsert(collection_name=collection_name, points=dummy_points)
    print(f"✅ Upserted {len(dummy_points)} AAPL points to '{collection_name}'.")

    # 4. Verify: search for AAPL (NEW API)
    print("\n🔍 Verifying by searching for AAPL...")
    search_results = client.query_points(
        collection_name=collection_name,
        query=generate_dummy_embedding(),  # vector query
        query_filter=Filter(must=[FieldCondition(key="ticker", match=MatchValue(value="AAPL"))]),
        limit=3,
    )

    # Print results
    for result in search_results.points:
        print(f"   - Score: {result.score:.3f}")
        print(f"     Ticker: {result.payload.get('ticker')}")
        print(f"     Price: ${result.payload.get('price'):.2f}")
        print(f"     Sentiment: {result.payload.get('sentiment')}")

    print("\n🎉 Ready for your TradingWorkflow tests!")


if __name__ == "__main__":
    main()
