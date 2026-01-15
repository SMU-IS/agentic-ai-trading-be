from pydantic import BaseModel, Field
from typing import Optional
# ---------- Pydantic request models ----------

class MarketOrderRequestBody(BaseModel):
    symbol: str
    side: str = Field(..., pattern="^(buy|sell)$")
    qty: Optional[float] = None
    notional: Optional[float] = None
    time_in_force: str = "day"


class LimitOrderRequestBody(BaseModel):
    symbol: str
    side: str = Field(..., pattern="^(buy|sell)$")
    limit_price: float
    qty: Optional[float] = None
    notional: Optional[float] = None
    time_in_force: str = "day"


class StopOrderRequestBody(BaseModel):
    symbol: str
    side: str = Field(..., pattern="^(buy|sell)$")
    stop_price: float
    qty: Optional[float] = None
    notional: Optional[float] = None
    time_in_force: str = "day"


class StopLimitOrderRequestBody(BaseModel):
    symbol: str
    side: str = Field(..., pattern="^(buy|sell)$")
    stop_price: float
    limit_price: float
    qty: Optional[float] = None
    notional: Optional[float] = None
    time_in_force: str = "day"


class BracketOrderRequestBody(BaseModel):
    symbol: str
    side: str = Field(..., pattern="^(buy|sell)$")
    qty: float
    entry_type: str = Field("market", pattern="^(market|limit)$")
    entry_price: Optional[float] = None
    take_profit_price: float
    stop_loss_price: float
    time_in_force: str = "day"


class ClosePositionRequestBody(BaseModel):
    percentage: Optional[float] = None
    qty: Optional[float] = None


class CloseAllPositionsRequestBody(BaseModel):
    cancel_orders: bool = True
