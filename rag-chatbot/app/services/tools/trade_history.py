import httpx
from langchain_core.tools import tool

from app.core.config import env_config
from app.schemas.chat import TradeHistory
from app.schemas.order_details import OrderDetailsResponse
from app.utils.logger import setup_logging

logger = setup_logging()


async def get_order_details(order_id: str):
    if not order_id:
        return {"error": "Error: No order_id provided."}

    order_detail = f"{env_config.order_details_query_url}/{order_id}"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(order_detail)
            response.raise_for_status()
            order_details = response.json()
            logger.info(f"Order details fetched for order {order_id}")

            return (
                order_details["symbol"],
                order_details["filled_avg_price"],
                order_details["side"],
                order_details["risk_evaluation"],
                order_details["risk_adjustments_made"],
                order_details["trading_agent_reasonings"],
            )

    except httpx.HTTPStatusError as exc:
        logger.error(
            f"HTTP error {exc.response.status_code} for order {order_id}: {exc.response.text}"
        )
        error_msg = f"API Error: {exc.response.status_code} while fetching news."
        raise Exception(error_msg)

    except httpx.RequestError as exc:
        logger.warning(f"Timeout reaching order service for ID: {order_id}")
        error_msg = f"Network Error: Could not reach the news service ({exc})."
        raise Exception(error_msg)

    except Exception as e:
        logger.exception(f"Unexpected error fetching order {order_id}")
        raise Exception(f"An unexpected error occurred: {str(e)}")


@tool(args_schema=TradeHistory)
async def get_trade_history_details(query: str, order_id: str) -> OrderDetailsResponse:
    """
    Retrieve deep-dive technical details and trade reasoning for a specific past transaction.

    Use this tool ONLY when:
    - The user asks "why" a specific trade was made (e.g., "Why did we sell AAPL?").
    - The user asks for the technical indicators (RSI, ATR) present at the time of a specific order.
    - The user provides a specific 'order_id' for performance lookup.

    Args:
        order_id (str): The unique identifier for the trade. This is mandatory.
                        If the user has not provided an ID, do not guess;
                        ask the user for it instead.

    Returns:
        A JSON string containing:
        - ticker: The stock symbol.
        - action: The trade direction (BUY/SELL).
        - entry_price: The price at execution.
        - reasoning: The specific technical justification (e.g., RSI/ATR values).
    """

    logger.info(f"User query: {query}. Analysing history for order {order_id}")

    try:
        (
            ticker,
            avg_price,
            action,
            _,
            _,
            trading_agent_reasoning,
        ) = await get_order_details(order_id)
    except Exception as e:
        logger.error(f"Failed to fetch order details for {order_id}: {e}")
        raise Exception(
            f"Could not retrieve trade history for order {order_id}: {str(e)}"
        )

    # TODO: KIV for Shawn
    return OrderDetailsResponse(
        ticker=ticker,
        action=action,
        entry_price=avg_price,
        reasoning=trading_agent_reasoning,
    )
