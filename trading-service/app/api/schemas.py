from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
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
    id: Optional[str] = Field(None, description="Signal ID")
    news_id: Optional[str] = Field(None, description="Original news / reddit post ID")
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
    timestamp: Optional[str] = Field(None, description="ISO creation timestamp (YYYY-MM-DDTHH:MM:SSZ)")

# Yahoo
class QuotesResponse(BaseModel):
    data: Dict[str, List[Dict[str, Any]]]


class HistoryResponse(BaseModel):
    symbol: str
    interval: str
    count: int
    bars: List[Dict[str, Any]]
    
class LatestInfoResponse(BaseModel):
    """Latest ticker price, quote, and metrics."""
    symbol: str
    timestamp: float
    price: Dict[str, float] = Field(..., description="Last, current, previous close")
    intraday: Dict[str, Any] = Field(..., description="OHLCV latest bar")
    averages: Dict[str, float] = Field(..., description="SMA 50/200")
    fundamentals: Dict[str, Any] = Field(..., description="Market cap, PE")
    change: Dict[str, float] = Field(..., description="Day % change")

class SignalResponse(BaseModel):     
    current_price: float   
    # OHLCV Raw
    open: float
    high: float
    low: float
    close: float
    adj_close: float
    volume: int
    
    # Candle Analysis (your core signals)
    candle_type: str  # 'strong_bullish', 'moderate_bearish', etc.
    body_size: float  # % body size
    body_pct: float   # body/range ratio
    upper_wick: float
    lower_wick: float
    
    # Technical Indicators
    rsi: float
    vol_ratio: float
    atr14: float
    sma20: Optional[float] = None
    sma50: Optional[float] = None
    sma200: Optional[float] = None
    golden_cross: bool = False
    death_cross: bool = False
    
    # Price Action Context
    high_3d: float
    low_3d: float
    is_penny: bool

    # market structure
    support: float
    resistance: float
    period_summary: str

    # MACD Fields
    macd: float
    macd_signal: float
    macd_histogram: float
    macd_bullish: bool = False
    macd_bearish: bool = False
    
    # Bollinger Bands Fields
    bb_upper: float
    bb_middle: float
    bb_lower: float
    bb_width: float
    bb_position: float  # 0=lower band, 1=upper band
    bb_squeeze: bool = False
    bb_upper_break: bool = False
    bb_lower_break: bool = False


# Trading DB - Alpaca account risk level
class RiskProfile(str, Enum):
    aggressive = "aggressive"
    conservative = "conservative"

class UpdateRiskProfileRequest(BaseModel):
    risk_profile: RiskProfile