import json

from langchain_core.tools import tool

from app.schemas.chat import TradeHistory


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
