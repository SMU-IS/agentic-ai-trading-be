import httpx
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from app.core.config import env_config
from app.schemas.chat import TradeHistory
from app.schemas.order_details import OrderDetailsResponse
from app.utils.logger import setup_logging

logger = setup_logging()


async def _fetch_order_data(order_id: str, user_id: str) -> dict:
    """Helper to fetch raw order details from the API."""
    if not order_id:
        raise ValueError("No order_id provided.")

    url = f"{env_config.order_details_query_url}/{order_id}"
    headers = {"x-user-id": user_id, "Content-Type": "application/json"}

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()


def _parse_order_details(data: dict) -> OrderDetailsResponse:
    """Helper to parse API response into OrderDetailsResponse."""
    return OrderDetailsResponse(
        ticker=data.get("symbol") or "Unknown",
        action=data.get("side") or "Unknown",
        entry_price=data.get("filled_avg_price") or 0.0,
        reasoning=data.get("trading_agent_reasonings")
        or "No specific reasoning provided.",
    )


@tool(args_schema=TradeHistory)
async def get_trade_history_details(
    order_id: str, config: RunnableConfig
) -> OrderDetailsResponse:
    """
    Retrieve deep-dive technical details and trade reasoning for a specific past transaction.

    Use this tool ONLY when:
    - The user asks "why" a specific trade was made.
    - The user asks for the technical indicators (RSI, ATR) at the time of a trade.
    - The user provides a specific 'order_id' for performance lookup.
    """

    logger.info(f"Analysing trade history order details for order id {order_id}")
    user_id = config.get("metadata", {}).get("user_id", "unknown-user")

    try:
        raw_data = await _fetch_order_data(order_id, user_id)
        return _parse_order_details(raw_data)

    except Exception as e:
        logger.error(f"Failed to fetch order details: {e}")
        raise Exception(f"Unable to retrieve trade history for {order_id}: {str(e)}")
