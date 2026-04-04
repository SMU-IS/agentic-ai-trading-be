from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    query: str
    order_id: str | None = None
    user_id: str | None = Field(None, description="Unique ID of the user (extracted from header if not provided)")
    session_id: str = Field(
        ..., description="Unique ID for the chat thread/conversation"
    )


class ChatHistoryResponse(BaseModel):
    history: list[dict] = Field(
        ..., description="The list of messages in the conversation"
    )


class ThreadResponse(BaseModel):
    thread_id: str = Field(..., description="Unique ID of the thread")
    title: str | None = Field(None, description="Title of the thread")
    updated_at: datetime = Field(..., description="Timestamp when thread was last updated")


class GeneralNews(BaseModel):
    query: str = Field(
        ...,
        description="The specific topic, question, or search string to look for in the news. e.g 'What is the latest news on Apple?'",
    )
    tickers: list[str] = Field(
        default_factory=list,
        description="Optional list of stock tickers (e.g. ['AAPL', 'TSLA']) if explicitly mentioned.",
    )


class TradeHistory(BaseModel):
    order_id: str = Field(
        ..., description="The order ID to get the previously executed trade history"
    )


class TradeHistoryRange(BaseModel):
    after: str = Field(..., description="Start date in YYYY-MM-DD format")
    until: str = Field(..., description="End date in YYYY-MM-DD format")


class TradeHistorySearch(BaseModel):
    ticker: Optional[str] = Field(None, description="The stock ticker mentioned (e.g. 'AAPL', 'GOOGL')")
    after: Optional[str] = Field(None, description="Start date in YYYY-MM-DD format")
    until: Optional[str] = Field(None, description="End date in YYYY-MM-DD format")
    order_id: Optional[str] = Field(None, description="A specific order ID mentioned or referred to (e.g. 'the first one', 'ORD123')")
