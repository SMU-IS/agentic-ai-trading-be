from pydantic import BaseModel
from typing import Dict, List, Optional, TypedDict, Any
from typing_extensions import NotRequired
from dataclasses import dataclass
from enum import Enum

class RiskProfile(str, Enum):
    CONSERVATIVE = "conservative"
    AGGRESSIVE   = "aggressive"

class Signal(BaseModel):
    signal_id: str

class SignalData(BaseModel):
    id: str
    ticker: str
    rumor_summary: str
    credibility: str
    credibility_reason: str
    references: List[str]
    trade_signal: str
    confidence: float
    trade_rationale: str
    position_size_pct: float
    stop_loss_pct: float
    target_pct: float
    news_id: str

@dataclass
class YahooTechnicalData:
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
    sma20: float
    sma50: float
    sma200: float
    golden_cross: bool
    death_cross: bool
    
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
    macd_bullish: bool
    macd_bearish: bool
    
    # Bollinger Bands Fields
    bb_upper: float
    bb_middle: float
    bb_lower: float
    bb_width: float
    bb_position: float  # 0=lower band, 1=upper band
    bb_squeeze: bool
    bb_upper_break: bool
    bb_lower_break: bool

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'YahooTechnicalData':
        """Create from raw dict - handles type conversion and missing fields."""
        
        # Field mapping with defaults
        field_map = {
            'current_price': data.get('current_price', data.get('Close', 0.0)),
            'open': float(data.get('open', 0.0)),
            'high': float(data.get('high', 0.0)),
            'low': float(data.get('low', 0.0)),
            'close': float(data.get('close', 0.0)),
            'adj_close': float(data.get('adj_close', 0.0)),
            'volume': int(data.get('volume', 0)),
            
            # Candle analysis
            'candle_type': data.get('candle_type', 'neutral'),
            'body_size': float(data.get('body_size', 0.0)),
            'body_pct': float(data.get('body_pct', 0.0)),
            'upper_wick': float(data.get('upper_wick', 0.0)),
            'lower_wick': float(data.get('lower_wick', 0.0)),
            
            # Technical indicators
            'rsi': float(data.get('rsi', 50.0)),
            'vol_ratio': float(data.get('vol_ratio', 1.0)),
            'atr14': float(data.get('atr14', 0.01)),
            'sma20': float(data.get('sma20', 0.0)) if data.get('sma20') is not None else None,
            'sma50': float(data.get('sma50', 0.0)) if data.get('sma50') is not None else None,
            'sma200': float(data.get('sma200', 0.0)) if data.get('sma200') is not None else None,
            'golden_cross': bool(data.get('golden_cross', False)),
            'death_cross': bool(data.get('death_cross', False)),
            
            # Price action
            'high_3d': float(data.get('high_3d', 0.0)),
            'low_3d': float(data.get('low_3d', 0.0)),
            'is_penny': bool(data.get('is_penny', False)),
            'support': float(data.get('support', 0.0)),
            'resistance': float(data.get('resistance', 0.0)),
            'period_summary': data.get('period_summary', 'N/A'),
            
            # MACD
            'macd': float(data.get('macd', 0.0)),
            'macd_signal': float(data.get('macd_signal', 0.0)),
            'macd_histogram': float(data.get('macd_histogram', 0.0)),
            'macd_bullish': bool(data.get('macd_bullish', False)),
            'macd_bearish': bool(data.get('macd_bearish', False)),
            
            # Bollinger Bands
            'bb_upper': float(data.get('bb_upper', 0.0)),
            'bb_middle': float(data.get('bb_middle', 0.0)),
            'bb_lower': float(data.get('bb_lower', 0.0)),
            'bb_width': float(data.get('bb_width', 0.0)),
            'bb_position': float(data.get('bb_position', 0.5)),
            'bb_squeeze': bool(data.get('bb_squeeze', False)),
            'bb_upper_break': bool(data.get('bb_upper_break', False)),
            'bb_lower_break': bool(data.get('bb_lower_break', False)),
        }
        
        return cls(**field_map)
    
    def to_prompt(self) -> str:
        def safe_format(value, fmt: str = "") -> str:
            """Format value safely, handles None."""
            if value is None:
                return "N/A"
            try:
                return f"{value:{fmt}}"
            except (ValueError, TypeError):
                return str(value)
            
        # Price context
        price_context = f"""
PRICE ACTION SUMMARY:
- Current: ${safe_format(self.current_price, '.3f')}
- Candle: {self.candle_type.upper()} (body {safe_format(self.body_size, '.1f')}%, {safe_format(self.body_pct, '.0%')} range)
- Range: ${safe_format(self.low, '.3f')} - ${safe_format(self.high, '.3f')} (ATR14: ${safe_format(self.atr14, '.3f')})
- Volume: {safe_format(self.vol_ratio, '.1f')}x average
"""
        
        # Technical summary
        rsi_status = "OVERSOLD" if self.rsi and self.rsi < 40 else "OVERBOUGHT" if self.rsi and self.rsi > 60 else "NEUTRAL"
        tech_context = f"""
TECHNICAL INDICATORS:
RSI: {safe_format(self.rsi, '.0f')} ({rsi_status})
Trend: SMA20: ${safe_format(self.sma20, '.3f')} | SMA50: ${safe_format(self.sma50, '.3f')} | SMA200: ${safe_format(self.sma200, '.3f')}
MACD: {safe_format(self.macd, '.4f')} vs Signal: {safe_format(self.macd_signal, '.4f')} (Histogram: {safe_format(self.macd_histogram, '+.4f')})
BB: {safe_format(self.bb_position, '.0%')} position (Lower: ${safe_format(self.bb_lower, '.3f')}, Upper: ${safe_format(self.bb_upper, '.3f')})
"""
        
        # Market structure
        structure = f"""
MARKET STRUCTURE:
Support: ${safe_format(self.support, '.3f')} | Resistance: ${safe_format(self.resistance, '.3f')}
3D Range: ${safe_format(self.low_3d, '.3f')} - ${safe_format(self.high_3d, '.3f')}
Penny Stock: {'YES' if self.is_penny else 'NO'}
Data Period: {self.period_summary}
"""

        prompt = f"""TRADING SIGNAL ANALYSIS
{price_context}
{tech_context}
{structure}
        """
        return prompt.strip()

@dataclass
class Quote:
    symbol: str
    bid_price: float
    bid_size: int
    ask_price: float
    ask_size: int
    timestamp: str  # ISO format
    conditions: List[str]
    tape: str

@dataclass
class Trade:
    symbol: str
    price: float
    size: int
    exchange: str
    conditions: List[str]
    timestamp: str  # ISO format
    id: str
    tape: str

@dataclass
class AlpacaData:
    """Alpaca live market data"""
    latest_quote: Quote
    latest_trade: Trade
    spread: float
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'AlpacaData':
        """Create from raw Alpaca dict"""
        return cls(
            latest_quote=Quote(**data['latest_quote']),
            latest_trade=Trade(**data['latest_trade']),
            spread=data['spread']
        )
    
    def to_prompt(self) -> str:
        """Convert to LLM-friendly prompt string"""
        trade = self.latest_trade
        quote = self.latest_quote
        spread_pct = 0.0
        if trade.price is not None and trade.price > 0:
            spread_pct = (self.spread / trade.price) * 100
        
        return f"""
LIVE QUOTE FROM BROKER ({trade.symbol}, {trade.timestamp}):
- Current Price: ${trade.price:.2f}
- Bid: ${quote.bid_price:.2f} x {quote.bid_size}
- Ask: ${quote.ask_price:.2f} x {quote.ask_size}
- Spread: ${self.spread:.3f} ({spread_pct:.1f}%)
"""


@dataclass
class MarketData:
    alpaca: AlpacaData
    yahoo: YahooTechnicalData
    timestamp: float  # Unix time from asyncio.get_event_loop().time()
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MarketData':
        """Create from raw state dict"""
        return cls(
            alpaca=AlpacaData.from_dict(data['alpaca']),
            yahoo=YahooTechnicalData.from_dict(data['yahoo']),
            timestamp=data['timestamp']
        )
    
    def to_prompt(self) -> str:
        """Full market data prompt for LLM"""
        return f"""{self.yahoo.to_prompt()}
{self.alpaca.to_prompt()}

Use this fresh market data to inform your trading decision."""


class TradeAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL" 
    HOLD = "HOLD"


@dataclass
class TradingDecision:
    """Trading decision output from LLM/workflow"""
    action: TradeAction  # BUY | SELL | HOLD
    confidence: float  # 0.0-1.0
    entry_price: float
    stop_loss: float
    take_profit: float
    qty: float
    risk_reward: str  # "X:1" format
    thesis: str  # Detailed reasoning with market data justification
    current_stock_price: float  # From market data
    ticker: Optional[str] = None 
    @classmethod
    def from_dict(cls, data: dict) -> 'TradingDecision':
        """Create from LLM JSON output"""
        return cls(
            action=TradeAction(data['action']),
            confidence=data['confidence'],
            entry_price=data['entry_price'],
            stop_loss=data['stop_loss'],
            take_profit=data['take_profit'],
            qty=data['qty'],
            risk_reward=data['risk_reward'],
            thesis=data['thesis'],
            current_stock_price=data['current_stock_price']
        )

    def to_prompt(self) -> str:
        """Format for logging/display"""
        return f"""🎯 TRADE DECISION
Action: {self.action} ({self.confidence:.1%})
Entry: ${self.entry_price:.2f} | SL: ${self.stop_loss:.2f} | TP: ${self.take_profit:.2f}
Qty: {self.qty} | R:R {self.risk_reward}
Price: ${self.current_stock_price:.2f}

{self.thesis}"""    


@dataclass
class RiskMetrics:
    risk_score: float
    risk_per_share: str  # "$X.XX"
    reward_per_share: str  # "$X.XX" 
    actual_rr: str  # "X.X:1"
    total_risk: str  # "$X (X.X%)"
    suggested_qty: str  # "X"
    near_resistance: bool
    atr_distance: str  # "X.X"
    max_risk_5pct: str  # "$X"
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RiskMetrics':
        return cls(**data)

@dataclass 
class RiskAssessment:
    """Risk management output"""
    risk_status: str  # "APPROVED" | "REVIEW"
    risk_score: float
    adjusted_trade: TradingDecision
    metrics: RiskMetrics
    issues: List[str]
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RiskAssessment':
        """Convert raw dict to typed object"""
        return cls(
            risk_status=data['risk_status'],
            risk_score=data['risk_score'],
            adjusted_trade=TradingDecision.from_dict(data['adjusted_trade']),
            metrics=RiskMetrics.from_dict(data['metrics']),
            issues=data['issues']
        )
    
    def to_string(self) -> str:
        """Readable summary"""
        status_emoji = "✅" if self.risk_status == "APPROVED" else "⚠️"
        return f"""{status_emoji} RISK ASSESSMENT
Status: {self.risk_status} (Score: {self.risk_score})
Suggested Qty: {self.metrics.suggested_qty}
Total Risk: {self.metrics.total_risk}
R:R: {self.metrics.actual_rr}

Issues: {', '.join(self.issues) if self.issues else 'None'}"""

class closed_position(TypedDict):
    qty: float
    side: str
    market_value: float
    avg_entry_price: float
    pnl: float


class db_trade_decision(TypedDict):
    order_id: str
    symbol: str
    action: str
    reasonings: str
    closed_position: NotRequired[Optional[closed_position]]
    signal_id: str
    
class risk_evaluation_result(TypedDict):
    adjusted_order_details: Optional[Dict[str, Any]]
    risk_evaluation: Optional[Dict[str, Any]]
    confidence: Optional[float]
    risk_score: Optional[float]

class RiskAdjResult(TypedDict):
    user_id: str
    adjusted_order_details: TradingDecision
    risk_evaluation: RiskAssessment
    should_execute: NotRequired[bool]
    conflict_resolution: NotRequired[Optional[Dict[db_trade_decision, Any]]]
    profile: NotRequired[RiskProfile]

class AgentState(TypedDict):
    # lookup node
    signal_id: str
    signal_data: SignalData

    # Market data from node_fetch_market_data
    market_data: MarketData

    # Output from reasoning
    order_details: TradingDecision
    has_trade_opportunity: NotRequired[bool]
    
    # Output from risk adjustment
    aggressive_adj_order_details: RiskAdjResult
    conservative_adj_order_details: RiskAdjResult

    ## adjusted_order_details: TradingDecision
    ## risk_evaluation: RiskAssessment
    should_execute: NotRequired[bool]

    # Save to db
    # execution_order_id: NotRequired[Optional[str]]
    # aggressive_execution_result:     NotRequired[Optional[Dict[str, Any]]]
    # conservative_execution_result:   NotRequired[Optional[Dict[str, Any]]]
    # execution_logs_by_user:   NotRequired[Optional[Dict[str, Any]]]
    # Conlfict resolution
    ## conflict_resolution: NotRequired[Optional[Dict[db_trade_decision, Any]]]
    # trading_accounts: NotRequired[Optional[Dict[str, Any]]]
    
    order_list:     NotRequired[list[RiskAdjResult]]
    execution_results:  NotRequired[list[dict]]


# Risk adjustment layer
@dataclass(frozen=True)
class ProfileParams:
    # Entry gates
    penny_block:        bool
    min_confidence:     float
    max_entry_dev_pct:  float   # fractional, e.g. 0.01 = 1%
    min_rr:             float
    min_vol_ratio:      float   # 0.0 = no block

    # SL/TP ATR multipliers
    sl_atr_mult:        float
    tp_atr_mult:        float

    # Position sizing
    max_risk_pct:       float   # fraction of account, e.g. 0.005
    max_position_pct:   float   # fraction of account, e.g. 0.02

    # Volume penalty
    low_vol_qty_mult:   float   # 1.0 = no reduction