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
    Uses LLM to extract parameters (query, tickers, dates) then fetches news.
    """
    logger.info("Executing general_news_node")

    from app.schemas.chat import GeneralNews
    from app.services.tools.general_news import get_general_news

    msg_id = str(uuid.uuid4())
    current_date = "2026-04-07"

    try:
        # 1. Extract structured parameters from the user query
        extraction_prompt = (
            f"Current date is {current_date}. "
            "Extract search parameters for market news from the user query. "
            "If the user mentions 'today', set start_date and end_date for today. "
            "If the user mentions 'yesterday', set start_date and end_date for yesterday. "
            "Dates should be in ISO format (YYYY-MM-DDTHH:MM:SS)."
        )

        structured_llm = llm.with_structured_output(GeneralNews)
        extracted_params = await structured_llm.ainvoke([
            SystemMessage(content=extraction_prompt),
            *state["messages"][-3:],
        ])

        logger.info(f"Extracted parameters: {extracted_params}")

        # 2. Fetch news using the extracted parameters
        result = await get_general_news.ainvoke({
            "query": extracted_params.query,
            "tickers": extracted_params.tickers,
            "start_date": extracted_params.start_date,
            "end_date": extracted_params.end_date,
        })
        logger.info(f"General news retrieved for query: {extracted_params.query}")

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
