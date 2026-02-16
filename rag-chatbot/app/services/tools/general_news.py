from typing import List

import httpx
from langchain_core.tools import tool

from app.core.config import env_config
from app.schemas.chat import GeneralNews


@tool(args_schema=GeneralNews)
async def get_general_news(query: str, tickers: List[str]):
    """
    Search and analyse recent financial news, market sentiment, and hot stocks.

    Use this tool when:
    - The user asks about general market trends or "what is happening today."
    - The user mentions "hot stocks," "top gainers," or "market sentiment."
    - The user asks about news specific to one or more tickers (e.g., "What's the news on NVDA and TSLA?").

    Args:
        query (str): The specific topic or question to search news for.
        tickers (List[str]): A list of stock symbols (e.g. ["AAPL", "TSLA"]).
                                       Pass an empty list [] if no specific tickers are mentioned.

    Returns:
        A dictionary containing a structured 'context' string for final responses
        and the raw 'results' list for deeper technical analysis.
    """

    payload = {
        "query": query,
        "limit": 5,
        "tickers": tickers if tickers is not None else [],
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                env_config.news_analysis_query_url, json=payload
            )
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])

            if not results:
                context = "No relevant news found for the requested tickers."
            else:
                context = "\n\n".join(
                    [
                        f"Headline: {d.get('headline', 'No headline')}\nContent: {d.get('content_preview', 'No content preview')}"
                        for d in results
                    ]
                )
            return {"context": context, "results": results}

    except httpx.HTTPStatusError as exc:
        error_msg = f"API Error: {exc.response.status_code} while fetching news."
        return {"context": error_msg, "results": []}

    except httpx.RequestError as exc:
        error_msg = f"Network Error: Could not reach the news service ({exc})."
        return {"context": error_msg, "results": []}

    except Exception as e:
        return {"context": f"An unexpected error occurred: {str(e)}", "results": []}
