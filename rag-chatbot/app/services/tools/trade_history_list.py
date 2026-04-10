from typing import Any, Dict, List

import httpx
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from app.core.config import env_config
from app.schemas.chat import TradeHistoryRange
from app.schemas.order_details import OrderSummary, TradeHistoryListResponse
from app.utils.logger import setup_logging

logger = setup_logging()


async def _fetch_raw_trade_history(
    after: str, until: str, user_id: str
) -> List[Dict[str, Any]]:
    """Fetches raw trade data from the order details service."""

    if not after or not until:
        raise ValueError("Both 'after' and 'until' dates are required.")

    url = f"{env_config.order_details_query_url}/all"
    params = {"after": after, "until": until}
    headers = {"x-user-id": user_id, "Content-Type": "application/json"}

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params, headers=headers)
        response.raise_for_status()
        return response.json()


def _transform_to_order_summaries(
    orders_data: List[Dict[str, Any]],
) -> List[OrderSummary]:
    """Transforms raw API response into a list of OrderSummary objects."""

    return [
        OrderSummary(
            id=o.get("id", "Unknown"),
            symbol=o.get("symbol", "Unknown"),
            side=o.get("side", "Unknown"),
            filled_avg_price=o.get("filled_avg_price"),
            created_at=o.get("created_at", "Unknown"),
        )
        for o in orders_data
    ]


@tool(args_schema=TradeHistoryRange)
async def get_trade_history_list(
    after: str, until: str, config: RunnableConfig
) -> TradeHistoryListResponse:
    """
    Retrieve a list of trades executed within a specific date range.

    Use this tool ONLY when:
    - The user asks to see their trade history or list of orders for a period of time.
    - Examples: "Show me the trades for the past 1 day", "List my orders from last week".

    Args:
        after (str): Start date in YYYY-MM-DD format.
        until (str): End date in YYYY-MM-DD format.
    """

    logger.info(f"Fetching trade history list from {after} to {until}")
    user_id = config.get("metadata", {}).get("user_id", "unknown-user")

    try:
        raw_orders = await _fetch_raw_trade_history(after, until, user_id)
        orders = _transform_to_order_summaries(raw_orders)
        return TradeHistoryListResponse(orders=orders)

    except Exception as e:
        logger.error(f"Failed to fetch trade history list: {e}")
        raise Exception(f"Unable to retrieve trade history: {str(e)}")
