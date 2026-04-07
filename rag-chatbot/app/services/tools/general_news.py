from typing import List, Optional

import httpx
from langchain_core.tools import tool

from app.core.config import env_config
from app.schemas.chat import GeneralNews


@tool(args_schema=GeneralNews)
async def get_general_news(
    query: str,
    tickers: Optional[List[str]] = [],
    is_general_market: bool = False,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """
    Search and analyze real-time financial news, market sentiment, and sector trends.

    CRITICAL USAGE RULES:
    1. Use ONLY for market-related research (e.g., "What's the news on AAPL?", "Why is the market down?").
    2. DO NOT use for meta-questions about the conversation history.
    3. DO NOT use for general greetings or non-financial chitchat.
    4. If the user mentions specific tickers, you CAN pass them in the 'tickers' list for better accuracy,
       otherwise the search will infer them from the query.

    Args:
        query (str): The search phrase. Focus on technical events (e.g., "earnings beat," "fed rate hike").
        tickers (List[str], optional): Stock symbols in uppercase (e.g. ["NVDA", "PLTR"]).
        is_general_market (bool): True if asking about overall market news, False otherwise.
        start_date (str, optional): Start date for filtering news (e.g. '2026-04-01T00:00:00').
        end_date (str, optional): End date for filtering news (e.g. '2026-04-07T23:59:59').

    Returns:
        dict: {
            "context": "A human-readable summary of headlines and content for immediate response.",
            "results": "Raw list of news objects for deeper technical/sentiment cross-referencing."
        }
    """

    try:
        async with httpx.AsyncClient() as client:
            # 1. Use /news (GET) only if explicitly flagged as a general market query
            if is_general_market:
                base_url = env_config.qdrant_retrieval_query_url.replace(
                    "/query", "/news"
                )
                params = {"start_date": start_date}
                if end_date:
                    params["end_date"] = end_date

                response = await client.get(base_url, params=params)

            # 2. Use /query (POST) for ticker-specific or topic-specific searches
            else:
                payload = {
                    "query": query,
                    "limit": 50,
<<<<<<< HEAD
                    "tickers": tickers if tickers is not None else [],
=======
                    "tickers": tickers if tickers else [],
>>>>>>> 38226ca541298a4c55a718e7b29d647a2c710bfa
                }
                if start_date:
                    payload["start_date"] = start_date
                if end_date:
                    payload["end_date"] = end_date

                response = await client.post(
                    env_config.qdrant_retrieval_query_url, json=payload
                )

            response.raise_for_status()
            data = response.json()
            results = (
                data.get("data", [])
                if isinstance(data, dict)
                else (data if isinstance(data, list) else [])
            )

            if not results:
                context = "No relevant news found for the request."
            else:
                formatted_news = []
                for d in results:
                    meta = d.get("metadata", {})
                    headline = meta.get("headline") or d.get("headline", "News Update")
                    content = (
                        d.get("text_content")
                        or meta.get("text_content")
                        or "No content available"
                    )
                    source = meta.get("source_domain", "Unknown source")
                    timestamp = meta.get("timestamp", "N/A")

                    formatted_news.append(
                        f"Headline: {headline}\n"
                        f"Source: {source} ({timestamp})\n"
                        f"Content: {content}"
                    )

                context = "\n\n---\n\n".join(formatted_news)

            return {"context": context, "results": results}

    except httpx.HTTPStatusError as exc:
        error_msg = f"API Error: {exc.response.status_code} while fetching news."
        return {"context": error_msg, "results": []}

    except httpx.RequestError as exc:
        error_msg = f"Network Error: Could not reach the news service ({exc})."
        return {"context": error_msg, "results": []}

    except Exception as e:
        return {"context": f"An unexpected error occurred: {str(e)}", "results": []}
