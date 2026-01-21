from app.agents.state import AgentState
from app.core.qdrant import QdrantManager
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.http.models import FieldCondition, Filter, MatchValue


async def node_lookup_qdrant(state: AgentState):
    """
    Memory: Fetches historical context or news related to the ticker.
    """

    print(f"   [🔍 Qdrant] Searching for historical context on {state['ticker']}...")

    qdrant_client = QdrantManager.get_client()
    try:
        query_filter = Filter(
            must=[FieldCondition(key="ticker", match=MatchValue(value=state["ticker"]))]
        )

        if "query_vector" not in state:
            import numpy as np

            state["query_vector"] = np.random.rand(10).tolist()
            print("   [🔍 Qdrant] Generated dummy query vector.")

        search_results = await qdrant_client.query_points(
            collection_name="historical_data",
            query=state["query_vector"],
            query_filter=query_filter,
            limit=5,
        )

        results = search_results.points

        state["historical_context"] = [
            {
                "id": result.id,
                "score": result.score,
                "payload": result.payload,
            }
            for result in results
        ]
        print(f"   [✅ Qdrant] Retrieved {len(results)} results for {state['ticker']}.")

    except (UnexpectedResponse, Exception) as e:
        print(f"   [❌ Qdrant Error] Could not connect or query failed: {e}")

        state["historical_context"] = []

    finally:
        await qdrant_client.close()

    return state
