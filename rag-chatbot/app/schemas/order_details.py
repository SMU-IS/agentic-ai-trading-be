from pydantic import BaseModel


# TODO: Update Schema
class OrderDetailsResponse(BaseModel):
    ticker: str
    action: str
    entry_price: float
    reasoning: str


class OrderSummary(BaseModel):
    id: str
    symbol: str
    side: str
    filled_avg_price: float | None
    created_at: str


class TradeHistoryListResponse(BaseModel):
    orders: list[OrderSummary]
