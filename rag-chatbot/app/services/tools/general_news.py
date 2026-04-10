from typing import Any, Dict, List, Optional

import httpx
from langchain_core.tools import tool

from app.core.config import env_config
from app.schemas.chat import GeneralNews


async def _fetch_news_from_api(
    client: httpx.AsyncClient,
    query: str,
    tickers: List[str],
    is_general_market: bool,
    start_date: Optional[str],
    end_date: Optional[str],
) -> List[Dict[str, Any]]:
    """Helper to fetch raw data from the news/query API."""

    if is_general_market:
        base_url = env_config.qdrant_retrieval_query_url.replace("/query", "/news")
        params = {"start_date": start_date}
        if end_date:
            params["end_date"] = end_date
        response = await client.get(base_url, params=params)
    else:
        payload = {
            "query": query,
            "limit": 50,
            "tickers": tickers,
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

    if isinstance(data, dict):
        return data.get("data") or data.get("results") or []
    return data if isinstance(data, list) else []


def _format_news_results(results: List[Dict[str, Any]]) -> str:
    """Helper to format raw news results into a readable string."""

    if not results:
        return "No relevant news found for the request."

    formatted_news = []
    for d in results:
        meta = d.get("metadata", {})
        headline = meta.get("headline") or d.get("headline", "News Update")
        content = (
            d.get("text_content") or meta.get("text_content") or "No content available"
        )
        source = meta.get("source_domain") or "Unknown source"
        timestamp = meta.get("timestamp") or "N/A"

        # Fallback for source if missing from metadata but in topic_id
        if source == "Unknown source" and "topic_id" in d:
            tid = d["topic_id"]
            if ":" in tid:
                source = tid.split(":")[0].replace("_", " ").title()

        formatted_news.append(
            f"Headline: {headline}\nSource: {source} ({timestamp})\nContent: {content}"
        )

    return "\n\n---\n\n".join(formatted_news)


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
    1. Use ONLY for market-related research.
    2. DO NOT use for meta-questions about conversation history or greetings.
    3. Pass specific tickers in 'tickers' for better accuracy.

    Args:
        query (str): The search phrase. Focus on technical events.
        tickers (List[str], optional): Stock symbols in uppercase (e.g. ["NVDA"]).
        is_general_market (bool): True if asking about overall market news.
        start_date (str, optional): Start date for filtering (ISO format).
        end_date (str, optional): End date for filtering (ISO format).
    """

    try:
        async with httpx.AsyncClient() as client:
            results = await _fetch_news_from_api(
                client, query, tickers or [], is_general_market, start_date, end_date
            )
            context = _format_news_results(results)
            return {"context": context, "results": results}

    except httpx.HTTPStatusError as exc:
        return {"context": f"API Error: {exc.response.status_code}", "results": []}
    except httpx.RequestError as exc:
        return {"context": f"Network Error: {str(exc)}", "results": []}
    except Exception as e:
        return {"context": f"Unexpected error: {str(e)}", "results": []}
