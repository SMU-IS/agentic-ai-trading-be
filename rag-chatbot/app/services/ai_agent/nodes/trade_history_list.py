import json
import uuid
from datetime import datetime
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage

from app.schemas.chat import TradeHistoryRange
from app.services.ai_agent.state import AgentState
from app.utils.logger import setup_logging

logger = setup_logging()


async def trade_history_list_node(state: AgentState, llm) -> dict[str, Any]:
    """
    Node to handle trade history list queries (e.g. "past 1 day").

    This node uses the LLM to extract the requested date range and then calls the trade history list tool.
    """
    logger.info("Executing trade_history_list_node")

    _ = state.get("query", "")
    msg_id = str(uuid.uuid4())

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    weekday = now.strftime("%A")

    extraction_instructions = (
        f"You are a date extraction assistant. Today's date is {today} ({weekday}).\n"
        "Extract the requested 'after' and 'until' dates in YYYY-MM-DD format from the user query.\n"
        "If they say 'past 1 day', 'after' should be yesterday and 'until' should be today.\n"
        "If they say 'today', both should be today.\n"
        "Return the 'after' and 'until' dates."
    )

    try:
        structured_llm = llm.with_structured_output(TradeHistoryRange)
        date_range = await structured_llm.ainvoke(
            [
                SystemMessage(content=extraction_instructions),
                *state["messages"][-3:],
            ]
        )

        logger.info(f"Extracted date range: {date_range.after} to {date_range.until}")

        from app.services.tools.trade_history_list import get_trade_history_list

        result = await get_trade_history_list.ainvoke(
            {"after": date_range.after, "until": date_range.until}
        )

        logger.info(
            f"Trade history list retrieved for period: {date_range.after} to {date_range.until}"
        )

        return {
            "messages": [SystemMessage(content=json.dumps(result.dict()), id=msg_id)],
        }

    except Exception as e:
        logger.error(f"Error fetching trade history list: {e}")
        return {
            "messages": [
                AIMessage(
                    content=f"Unable to retrieve your trade history list: {str(e)}",
                    id=msg_id,
                )
            ]
        }
