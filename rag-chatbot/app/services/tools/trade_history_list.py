import httpx
from langchain_core.tools import tool

from app.core.config import env_config
from app.schemas.chat import TradeHistoryRange
from app.schemas.order_details import OrderSummary, TradeHistoryListResponse
from app.utils.logger import setup_logging

logger = setup_logging()


async def _get_trade_history_list(after: str, until: str):
    if not after or not until:
        logger.error("Missing 'after' or 'until' date for trade history list query.")
        raise ValueError("Both 'after' and 'until' dates are required.")

    url = f"{env_config.order_details_query_url}/all"
    params = {"after": after, "until": until}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            orders = response.json()
            logger.info(f"Orders fetched for period {after} to {until}")
            return orders

    except httpx.HTTPStatusError as exc:
        logger.error(
            f"HTTP error {exc.response.status_code} for trade history list: {exc.response.text}"
        )
        error_msg = f"API Error: {exc.response.status_code} while fetching orders."
        raise Exception(error_msg)

    except httpx.RequestError as exc:
        logger.warning(
            f"Timeout reaching order service for trade history list query: {exc}"
        )
        error_msg = f"Network Error: Could not reach the order service ({exc})."
        raise Exception(error_msg)

    except Exception as e:
        logger.exception("Unexpected error fetching trade history list")
        raise Exception(f"An unexpected error occurred: {str(e)}")


@tool(args_schema=TradeHistoryRange)
async def get_trade_history_list(after: str, until: str) -> TradeHistoryListResponse:
    """
    Retrieve a list of trades executed within a specific date range.

    Use this tool ONLY when:
    - The user asks to see their trade history or list of orders for a period of time.
    - Examples: "Show me the trades for the past 1 day", "List my orders from last week".

    Args:
        after (str): Start date in YYYY-MM-DD format.
        until (str): End date in YYYY-MM-DD format.

    Returns:
        A list of orders with their IDs, symbols, prices, and creation dates.
    """

    logger.info(f"Fetching trade history list from {after} to {until}")

    try:
        orders_data = await _get_trade_history_list(after, until)

        # Transform the data into the expected format
        orders = []
        for o in orders_data:
            orders.append(
                OrderSummary(
                    id=o.get("id", "Unknown"),
                    symbol=o.get("symbol", "Unknown"),
                    side=o.get("side", "Unknown"),
                    filled_avg_price=o.get("filled_avg_price"),
                    created_at=o.get("created_at", "Unknown"),
                )
            )

        return TradeHistoryListResponse(orders=orders)

    except Exception as e:
        logger.error(f"Failed to fetch trade history list: {e}")
        raise Exception(
            f"Unable to retrieve trade history for the period {after} to {until}. "
            "Please ensure the dates are correct and try again."
        )
