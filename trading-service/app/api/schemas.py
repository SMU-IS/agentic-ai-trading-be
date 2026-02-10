from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum
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
    extended_hours: bool = True


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

class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"

class EntryType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"

class TimeInForce(str, Enum):
    DAY = "day"
    GTC = "gtc"
    OPG = "opg"
    CLS = "cls"
    IOC = "ioc"
    FOK = "fok"
    
class BracketOrderRequestBody(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=10)
    side: OrderSide
    qty: float = Field(..., gt=0)
    entry_type: EntryType = EntryType.MARKET
    entry_price: Optional[float] = Field(None, ge=0)
    take_profit_price: float = Field(..., gt=0)
    stop_loss_price: float = Field(..., gt=0)
    time_in_force: TimeInForce = TimeInForce.DAY


class ClosePositionRequestBody(BaseModel):
    percentage: Optional[float] = None
    qty: Optional[float] = None


class CloseAllPositionsRequestBody(BaseModel):
    cancel_orders: bool = True


class HistoricalPoint(BaseModel):
    date: str        # "2025-05-01T00:00:00.000Z"
    value: float     # 30.52

class PortfolioHistoryResponse(BaseModel):
    historical: List[HistoricalPoint]
    
# Trading_db (signals) models
class Credibility(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium" 
    HIGH = "High"

class TradeSignal(str, Enum):
    BUY = "BUY"
    SHORT = "SHORT"
    NO_TRADE = "NO_TRADE"
    
class DeepAnalysis(BaseModel):
    ticker: str = Field(..., description="Stock ticker")
    rumor_summary: str = Field(..., description="1-sentence recap")
    credibility: Credibility = Field(..., description="Low|Medium|High")
    credibility_reason: str = Field(..., description="2-3 sentences")
    references: List[str] = Field(default_factory=list, description="URLs/sources")
    trade_signal: TradeSignal = Field(..., description="BUY|SHORT|NO_TRADE")
    confidence: int = Field(..., description="1-10 scale")
    trade_rationale: str = Field(..., description="Why this signal")
    position_size_pct: float = Field(..., description="0.5|1|2")
    stop_loss_pct: float = Field(..., description="8|10|12")
    target_pct: float = Field(..., description="20|30|50")