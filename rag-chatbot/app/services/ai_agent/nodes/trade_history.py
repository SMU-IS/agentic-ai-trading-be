import json
import uuid
from typing import Any

from langchain_core.messages import AIMessage

from app.services.ai_agent.state import AgentState
from app.utils.logger import setup_logging

logger = setup_logging()


async def trade_history_node(state: AgentState) -> dict[str, Any]:
    """
    Node to handle trade history queries.

    This node is executed when the user query contains an order_id.
    It extracts the order_id from state and calls the trade history tool.

    Args:
        state: The current agent state

    Returns:
        Updated state with the trade history response
    """
    logger.info("Executing trade_history_node")

    order_id = state.get("order_id")
    msg_id = str(uuid.uuid4())
    if not order_id:
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

    try:
        from app.services.tools.trade_history import get_trade_history_details

        result = await get_trade_history_details.ainvoke({"order_id": order_id})
        logger.info(f"Trade history retrieved for order_id: {order_id}")
        return {
            "messages": [AIMessage(content=json.dumps(result.dict()), id=msg_id)],
        }

    except Exception as e:
        logger.error(f"Error fetching trade history for {order_id}: {e}")
        return {
            "messages": [
                AIMessage(
                    content=f"Unable to retrieve trade history for order {order_id}. "
                    f"Error: {str(e)}",
                    id=msg_id,
                )
            ]
        }
