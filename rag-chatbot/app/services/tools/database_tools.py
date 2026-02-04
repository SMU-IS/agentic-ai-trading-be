import json

import httpx
from langchain_core.tools import tool


@tool
def get_agent_m_transactions(order_id: str):
    """
    Queries Postgres Database for specific trade details (entry price, reasoning, technicals).
    Use this when the user asks 'why' about a specific order.
    """
    return json.dumps(
        {
            "ticker": "AAPL",
            "action": "SELL",
            "entry_price": 248.04,
            "reasoning": "Bearish RSI divergence (55.32) and missed earnings.",
        }
    )  # hardcoded for now


@tool
async def get_general_news_context_and_result(self, inputs: dict):
    """
    Calls the external news-analysis service to retrieve news context and results.
    """

    payload = {
        "query": inputs.get("query", ""),
        "limit": 5,
        "ticker_filter": inputs.get("tickers", []),
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(self.qdrant_db_url, json=payload)
        response.raise_for_status()
        data = response.json()
        results = data.get("results", [])

        if not results:
            context = "No relevant news found for the requested tickers."
        else:
            context = "\n\n".join(
                [
                    f"Headline: {d.get('headline', 'No headline')}\nContent: {d.get('content_preview', 'No content preview')}"
                    for d in results
                ]
            )
        return {"context": context, "results": results}
