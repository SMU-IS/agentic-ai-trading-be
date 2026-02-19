from src.config import settings
from typing import Dict, Any
import httpx
NEWS_ANALYSIS_QDRANT_URL = settings.news_analysis_qdrant_url

    
async def lookup_qdrant(ticker: str, event: str):
    """
    Memory: Fetches historical context or news related to the ticker.
    """
    qdrant_data = await get_qdrant_data(ticker, event)
    print("Qdrant data:", qdrant_data)
    return qdrant_data.get("results", [{"text_content": "No results found in qdrant"}])
    

async def get_qdrant_data(ticker: str, event: str) -> Dict[str, Any]:
    """Fetch Qdrant vector search results for ticker + event"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(
                NEWS_ANALYSIS_QDRANT_URL, 
                params={"ticker": ticker.lower(), "event_type": event, "limit": 10}
            )
            response.raise_for_status()
            return response.json()  # ✅ Raw response
        except httpx.HTTPStatusError as e:
            print(f"Qdrant HTTP {e.response.status_code}: {e.response.text[:200]}")
            return {"status": "error", "error": f"HTTP {e.response.status_code}"}
        except Exception as e:
            print(f"Qdrant error: {str(e)}")
            return {"status": "error", "error": str(e)}