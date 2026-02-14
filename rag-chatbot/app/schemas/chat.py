from typing import List

from pydantic import BaseModel, Field


class GeneralNews(BaseModel):
    query: str = Field(
        ...,
        description="The specific topic, question, or search string to look for in the news. e.g 'What is the latest news on Apple?'",
    )
    tickers: List[str] = Field(
        default=[],
        description="A list of stock tickers (e.g. ['AAPL', 'TSLA']) to get news for",
    )


class TradeHistory(BaseModel):
    query: str = Field(
        ...,
        description=(
            "A detailed summary of the position to be analysed, including the "
            "ticker/symbol, current price, shares, average entry price, and "
            "Profit/Loss (P/L) data provided by the user."
        ),
    )
    order_id: str = Field(
        ..., description="The order ID to get the previously executed trade history"
    )
