import datetime

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    query: str
    order_id: str | None = None
    user_id: str = Field(..., description="Unique ID of the user")
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
    updated_at: str = Field(..., description="Timestamp when thread was last updated")


class GeneralNews(BaseModel):
    query: str = Field(
        ...,
        description="The specific topic, question, or search string to look for in the news. e.g 'What is the latest news on Apple?'",
    )
    tickers: list[str] = Field(
        default=[],
        description="A list of stock tickers (e.g. ['AAPL', 'TSLA']) to get news for",
    )


class TradeHistory(BaseModel):
    order_id: str = Field(
        ..., description="The order ID to get the previously executed trade history"
    )
