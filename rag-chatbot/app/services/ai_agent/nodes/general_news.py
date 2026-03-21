import json
from typing import Any

from langchain_core.messages import AIMessage

from app.services.ai_agent.state import AgentState
from app.utils.logger import setup_logging

logger = setup_logging()


async def general_news_node(state: AgentState) -> dict[str, Any]:
    """
    Node to handle general news queries.

    This node is executed when the user query does not contain an order_id.
    It extracts tickers from the state and calls the general news tool.

    Args:
        state: The current agent state

    Returns:
        Updated state with the news response
    """
    logger.info("Executing general_news_node")

    query = state.get("query", "")
    tickers = (
        state.get("variables", {}).get("tickers", []) if state.get("variables") else []
    )

    try:
        from app.services.tools.general_news import get_general_news

        result = await get_general_news.ainvoke({"query": query, "tickers": tickers})
        logger.info("General news retrieved")

        return {
            "messages": [AIMessage(content=json.dumps(result))],
        }

    except Exception as e:
        logger.error(f"Error fetching general news: {e}")
        return {
            "messages": [
                AIMessage(content=f"An error occurred while fetching news: {str(e)}")
            ]
        }
