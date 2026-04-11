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

    # Limit to top 5 most relevant news to stay within context
    results = results[:5]

    formatted_news = []
    for d in results:
        meta = d.get("metadata", {})
        headline = meta.get("headline") or d.get("headline", "News Update")

        # Truncate content for each article
        content = (
            d.get("text_content") or meta.get("text_content") or "No content available"
        )
        MAX_CONTENT_LENGTH = 800
        if len(content) > MAX_CONTENT_LENGTH:
            content = content[:MAX_CONTENT_LENGTH] + "... [Truncated for brevity]"

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
    tickers: Optional[List[str]] = None,
    is_general_market: bool = False,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """
    Search and analyze real-time financial news, market sentiment, and sector trends.

    CRITICAL USAGE RULES:
    1. Use ONLY for market-related research and external news.
    2. DO NOT use this to check if you (the agent) have traded a stock. Use 'get_trade_history_list' for history.
    3. Pass specific tickers in 'tickers' for better accuracy.
    """

    try:
        async with httpx.AsyncClient() as client:
            results = await _fetch_news_from_api(
                client, query, tickers or [], is_general_market, start_date, end_date
            )
            context = _format_news_results(results)
            # Only return the context and a small slice of results metadata to keep token count low
            return {
                "context": context,
                "results": [
                    {
                        "headline": r.get("metadata", {}).get("headline"),
                        "source": r.get("metadata", {}).get("source_domain"),
                    }
                    for r in results[:5]
                ],
            }

    except httpx.HTTPStatusError as exc:
        return {"context": f"API Error: {exc.response.status_code}", "results": []}
    except httpx.RequestError as exc:
        return {"context": f"Network Error: {str(exc)}", "results": []}
    except Exception as e:
        return {"context": f"Unexpected error: {str(e)}", "results": []}
