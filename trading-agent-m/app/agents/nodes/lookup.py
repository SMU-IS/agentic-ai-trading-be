from app.agents.state import AgentState, SignalData
from fastapi import HTTPException
import httpx
from app.core.config import env_config

TRADING_SERVICE_URL = env_config.trading_service_url

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
    print(url)
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