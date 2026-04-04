import json
import uuid
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage

from app.services.ai_agent.state import AgentState
from app.utils.logger import setup_logging

logger = setup_logging()


async def general_news_node(state: AgentState, llm) -> dict[str, Any]:
    """
    Node to handle general news queries.
    Passes data through LLM for formatting before returning.
    """
    logger.info("Executing general_news_node")

    query = state.get("query", "")
    msg_id = str(uuid.uuid4())

    try:
        from app.services.tools.general_news import get_general_news

        result = await get_general_news.ainvoke({"query": query})
        logger.info(f"General news retrieved for query: {query}")

        prompt = (
            "You are a helpful trading assistant. "
            "Format the following news data into a concise, professional summary for the user. "
            "Focus on the most relevant details."
        )

        response = await llm.ainvoke([
            SystemMessage(content=prompt),
            SystemMessage(content=json.dumps(result)),
            *state["messages"][-3:],
        ], config={"tags": ["user_response"]})

        return {
            "messages": [response],
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
