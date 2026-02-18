from app.agents.state import AgentState, SignalData
from app.core.qdrant import QdrantManager
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.http.models import FieldCondition, Filter, MatchValue
from fastapi import FastAPI, HTTPException
import httpx
import asyncio
from app.core.config import env_config

TRADING_SERVICE_URL = env_config.trading_service_url

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

async def node_fetch_signal_data(state: AgentState):
    """
    Fetches the signal data from Redis or another source based on signal_id.
    """
    print(f"   [📡 Fetch Signal] Fetching signal data for signal_id: {state['signal_id']}...") 
    state["signal_data"] = await get_signal_data(state["signal_id"])
    print(f"   [✅ Fetch Signal] Successfully fetched signal data for signal_id: {state['signal_id']}.")
    return state


async def get_signal_data(signal_id: str) -> SignalData:
    url = f"{TRADING_SERVICE_URL}/decisions/signals/{signal_id}"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            return SignalData(**data)
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=f"Trading decision fetch failed: {e}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Request error: {str(e)}")