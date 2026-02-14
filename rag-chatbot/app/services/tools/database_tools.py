import json
from typing import List

import httpx
from langchain_core.tools import tool

from app.core.config import env_config
from app.schemas.chat import GeneralNews, TradeHistory


@tool(args_schema=TradeHistory)
def get_trade_history_details(query: str, order_id: str):
    """
    Retrieve deep-dive technical details and trade reasoning for a specific past transaction.

    Use this tool ONLY when:
    - The user asks "why" a specific trade was made (e.g., "Why did we sell AAPL?").
    - The user asks for the technical indicators (RSI, ATR) present at the time of a specific order.
    - The user provides a specific 'order_id' for performance lookup.

    Args:
        order_id (str): The unique identifier for the trade. This is mandatory.
                        If the user has not provided an ID, do not guess;
                        ask the user for it instead.

    Returns:
        A JSON string containing:
        - ticker: The stock symbol.
        - action: The trade direction (BUY/SELL).
        - entry_price: The price at execution.
        - reasoning: The specific technical justification (e.g., RSI/ATR values).
    """

    print(f"User query: {query}. Analysing history for order {order_id}")

    # retrieve order details using order_id from postgres

    # TODO: hardcoded for now
    return json.dumps(
        {
            "ticker": "AAPL",
            "action": "SELL",
            "entry_price": 248.04,
            "reasoning": "Based on the news signal, AAPL has missed earnings expectations with a bearish sentiment score of -0.75. The recent historical data shows that the stock has been trending downwards since January 16th. The technical setup is also bearish, as the RSI (14) is at 55.32 and there's a bearish divergence between the price action and the RSI. Volatility is moderate, with an ATR of 4.35. Given the aggressive risk profile, we can enter short with a stop-loss at $251.56 (2x ATR from entry) and take-profit at $244.68 (1x ATR from entry). This trade has a risk-reward ratio of 2:1",
        }
    )


@tool(args_schema=GeneralNews)
async def get_general_news_context_and_result(query: str, tickers: List[str]):
    """
    Search and analyse recent financial news, market sentiment, and hot stocks.

    Use this tool when:
    - The user asks about general market trends or "what is happening today."
    - The user mentions "hot stocks," "top gainers," or "market sentiment."
    - The user asks about news specific to one or more tickers (e.g., "What's the news on NVDA and TSLA?").

    Args:
        query (str): The specific topic or question to search news for.
        tickers (Optional[List[str]]): A list of stock symbols (e.g. ["AAPL", "TSLA"]).
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

    async with httpx.AsyncClient() as client:
        response = await client.post(env_config.news_analysis_query_url, json=payload)
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
