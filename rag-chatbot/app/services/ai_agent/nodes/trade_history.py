import json
import uuid
from datetime import datetime
from typing import Any, Union

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.schemas.chat import TradeHistorySearch
from app.services.ai_agent.state import AgentState
from app.services.tools.trade_history import get_trade_history_details
from app.services.tools.trade_history_list import _get_trade_history_list
from app.utils.logger import setup_logging

logger = setup_logging()


async def trade_history_node(
    state: AgentState, config: RunnableConfig, llm
) -> dict[str, Any]:
    """
    Node to handle trade history queries.
    Coordinates between automatic order lookup and detail retrieval.
    """
    logger.info("Executing trade_history_node")

    order_id = state.get("order_id")
    msg_id = str(uuid.uuid4())

    # 1. Attempt automatic lookup if order_id is missing
    if not order_id:
        lookup_result = await _attempt_order_lookup(state, config, llm, msg_id)
        if isinstance(lookup_result, dict):
            return lookup_result
        order_id = lookup_result

    # 2. Return clarification request if still no order_id
    if not order_id:
        return _request_order_id_clarification(msg_id)

    # 3. Retrieve and format trade details
    return await _fetch_and_format_trade_details(order_id, config, msg_id)


async def _attempt_order_lookup(
    state: AgentState, config: RunnableConfig, llm, msg_id: str
) -> Union[str, dict[str, Any], None]:
    """Attempts to find a unique order_id using ticker and date extraction."""
    logger.info("No order_id found, attempting to find order by ticker and date")

    try:
        # Extract search criteria (ticker, dates, or a reference to an order)
        criteria = await _extract_search_criteria(state, llm)
        
        # If the LLM successfully resolved a reference (e.g. 'the first one') to an ID
        if criteria.order_id:
            logger.info(f"LLM resolved reference to order_id: {criteria.order_id}")
            return criteria.order_id

        if not (criteria.ticker and criteria.after and criteria.until):
            return None

        # Search for matching orders
        user_id = config.get("metadata", {}).get("user_id", "unknown-user")
        orders = await _get_trade_history_list(criteria.after, criteria.until, user_id)

        matching = [
            o for o in orders if o.get("symbol", "").upper() == criteria.ticker.upper()
        ]

        # Handle matching results
        if len(matching) == 1:
            unique_id = matching[0]["id"]
            logger.info(f"Found unique matching order: {unique_id}")
            return unique_id

        if len(matching) > 1:
            return _format_multiple_orders_response(criteria.ticker, matching, msg_id)

        return _format_no_orders_response(criteria, msg_id)

    except Exception as e:
        logger.error(f"Failed to find order automatically: {e}")
        return None


async def _extract_search_criteria(state: AgentState, llm) -> TradeHistorySearch:
    """Uses LLM to extract ticker and date range from conversation history."""
    now = datetime.now()
    today, weekday = now.strftime("%Y-%m-%d"), now.strftime("%A")

    instructions = (
        f"You are a trade information extraction assistant. Today's date is {today} ({weekday}).\n"
        "1. Extract the stock ticker and date range from the user query (e.g., 'AAPL', 'last week').\n"
        "2. If the user refers to a previous message (e.g., 'the first one', 'that buy order', 'ORD123'), "
        "resolve it to a concrete 'order_id' from the conversation history.\n"
        "Return the 'ticker', 'after', 'until' (YYYY-MM-DD), and 'order_id' if applicable."
    )

    structured_llm = llm.with_structured_output(TradeHistorySearch)
    return await structured_llm.ainvoke(
        [
            SystemMessage(content=instructions),
            *state["messages"][-3:],
        ]
    )


def _format_multiple_orders_response(ticker: str, orders: list, msg_id: str) -> dict[str, Any]:
    """Formats a clarification message when multiple matching orders are found."""
    
    order_items = []
    for i, o in enumerate(orders, 1):
        # Format date if possible (e.g. 2026-04-02T05:42... -> 2026-04-02)
        raw_date = o.get('created_at', 'Unknown date')
        display_date = raw_date.split('T')[0] if 'T' in raw_date else raw_date
        
        item = f"{i}. **{o['side'].upper()}** {o['symbol']} on {display_date} (ID: `{o['id']}`)"
        order_items.append(item)
    
    order_list_str = "\n".join(order_items)
    
    content = (
        f"I found {len(orders)} orders for **{ticker}** in that period. "
        "Which one are you interested in?\n\n"
        f"{order_list_str}"
    )
    
    return {
        "messages": [
            AIMessage(
                content=content,
                id=msg_id,
            )
        ]
    }


def _format_no_orders_response(
    criteria: TradeHistorySearch, msg_id: str
) -> dict[str, Any]:
    """Formats a message when no matching orders are found."""
    return {
        "messages": [
            AIMessage(
                content=f"I couldn't find any trades for {criteria.ticker} "
                f"between {criteria.after} and {criteria.until}.",
                id=msg_id,
            )
        ]
    }


def _request_order_id_clarification(msg_id: str) -> dict[str, Any]:
    """Requests the user to provide an order ID."""
    logger.warning("No order_id found in state for trade_history_node")
    return {
        "messages": [
            AIMessage(
                content="I couldn't find an order ID in your query. "
                "Please provide an order ID so I can retrieve the trade history.",
                id=msg_id,
            )
        ]
    }


async def _fetch_and_format_trade_details(
    order_id: str, config: RunnableConfig, msg_id: str
) -> dict[str, Any]:
    """Calls the trade history tool and formats the final system response."""
    try:
        result = await get_trade_history_details.ainvoke(
            {"order_id": order_id}, config=config
        )
        logger.info(f"Trade history retrieved for order_id: {order_id}")
        return {
            "messages": [SystemMessage(content=json.dumps(result.model_dump()), id=msg_id)],
            "order_id": order_id,
        }
    except Exception as e:
        logger.error(f"Error fetching trade history for {order_id}: {e}")
        return {
            "messages": [
                AIMessage(
                    content=f"Unable to retrieve trade history for order {order_id}. Error: {str(e)}",
                    id=msg_id,
                )
            ]
        }
