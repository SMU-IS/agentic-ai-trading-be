import json
import uuid
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage

from app.services.ai_agent.state import AgentState
from app.utils.logger import setup_logging

logger = setup_logging()


async def general_news_node(state: AgentState) -> dict[str, Any]:
    """
    Node to handle general news queries.

    This node is executed when the user query does not contain an order_id.
    It passes the query to the news tool, which performs retrieval.
    """
    logger.info("Executing general_news_node")

    query = state.get("query", "")
    msg_id = str(uuid.uuid4())

    try:
        from app.services.tools.general_news import get_general_news

        # Call the tool with just the query. The tool now handles tickers optionally.
        result = await get_general_news.ainvoke({"query": query})
        logger.info(f"General news retrieved {result}")

        return {
            "messages": [SystemMessage(content=json.dumps(result), id=msg_id)],
        }

    except Exception as e:
        logger.error(f"Error fetching general news: {e}")
        return {
            "messages": [
                AIMessage(
                    content=f"An error occurred while fetching news: {str(e)}",
                    id=msg_id,
                )
            ]
        }
