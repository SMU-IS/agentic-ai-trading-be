from pydantic import BaseModel


# TODO: Update Schema
class OrderDetailsResponse(BaseModel):
    ticker: str
    action: str
    entry_price: float
    reasoning: str | None = None


class OrderSummary(BaseModel):
    id: str
    symbol: str
    side: str
    filled_avg_price: float | None
    created_at: str


class TradeHistoryListResponse(BaseModel):
    orders: list[OrderSummary]
    total_count: int
    truncated: bool = False
    message: str | None = None
