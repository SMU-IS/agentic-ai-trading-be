import json

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
