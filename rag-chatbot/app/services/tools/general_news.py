from typing import List

import httpx
from langchain_core.tools import tool

from app.core.config import env_config
from app.schemas.chat import GeneralNews


@tool(args_schema=GeneralNews)
async def get_general_news(query: str, tickers: List[str]):
    """
    Search and analyze real-time financial news, market sentiment, and sector trends.

    CRITICAL USAGE RULES:
    1. Use ONLY for market-related research (e.g., "What's the news on AAPL?", "Why is the market down?").
    2. DO NOT use for meta-questions about the conversation history.
    3. DO NOT use for general greetings or non-financial chitchat.
    4. If the user mentions specific tickers, they MUST be passed in the 'tickers' list.
    5. If the query is about general market "vibes" or "hot stocks," pass an empty list [] for tickers.

    Args:
        query (str): The search phrase. Focus on technical events (e.g., "earnings beat," "fed rate hike").
        tickers (List[str]): Stock symbols in uppercase (e.g. ["NVDA", "PLTR"]). Empty list if N/A.

    Returns:
        dict: {
            "context": "A human-readable summary of headlines and content for immediate response.",
            "results": "Raw list of news objects for deeper technical/sentiment cross-referencing."
        }
    """

    payload = {
        "query": query,
        "limit": 5,
        "tickers": tickers if tickers is not None else [],
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                env_config.qdrant_retrieval_query_url, json=payload
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
