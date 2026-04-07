import json
import uuid
from datetime import datetime, timedelta
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

    # Get dynamic current date
    now = datetime.now()
    current_date_iso = now.strftime("%Y-%m-%dT%H:%M:%S")

    try:
        # 1. Extract structured parameters from the user query
        extraction_prompt = (
            f"Current date and time is {current_date_iso}. "
            "Extract search parameters for market news from the user query. "
            "Instructions:\n"
            "1. If the user mentions 'today', set start_date and end_date for today.\n"
            "2. If the user mentions 'yesterday', set start_date and end_date for yesterday.\n"
            "3. If the user mentions specific companies or topics (e.g., 'Apple', 'interest rates'), set 'is_general_market' to False.\n"
            "4. If the user is asking about the overall/general market sentiment, set 'is_general_market' to True.\n"
            "5. If the user does NOT mention a date or time period, leave start_date and end_date as null.\n"
            "Dates should be in ISO format (YYYY-MM-DDTHH:MM:SS)."
        )

        structured_llm = llm.with_structured_output(GeneralNews)
        extracted_params = await structured_llm.ainvoke([
            SystemMessage(content=extraction_prompt),
            *state["messages"][-3:],
        ])

        # 2. Handle defaults: If no date provided, default to yesterday
        start_date = extracted_params.start_date
        end_date = extracted_params.end_date

        if not start_date:
            yesterday = now - timedelta(days=1)
            yesterday_str = yesterday.strftime("%Y-%m-%d")
            start_date = f"{yesterday_str}T00:00:00"
            end_date = f"{yesterday_str}T23:59:59"
            logger.info(
                f"No date provided, defaulting to yesterday: {start_date} to {end_date}"
            )

        logger.info(
            f"Extracted parameters: query='{extracted_params.query}', tickers={extracted_params.tickers}, "
            f"is_general_market={extracted_params.is_general_market}, start_date='{start_date}', end_date='{end_date}'"
        )

        # 3. Fetch news using the parameters
        result = await get_general_news.ainvoke({
            "query": extracted_params.query,
            "tickers": extracted_params.tickers if extracted_params.tickers is not None else [],
            "is_general_market": extracted_params.is_general_market,
            "start_date": start_date,
            "end_date": end_date,
        })

        logger.info(f"General news retrieved for query: {extracted_params.query}. Content preview: {str(result.get('context', ''))[:200]}...")

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
