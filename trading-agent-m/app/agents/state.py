from pydantic import BaseModel
from typing import Dict, List, Optional, TypedDict, Any
from typing_extensions import NotRequired
from dataclasses import dataclass
from enum import Enum

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
class YahooData:
    """Yahoo Finance technical indicators data"""
    price: float
    atr14: float
    sma20: float
    sma50: float
    support: float
    resistance: float
    rsi14: float
    
    summary: str  # "62 bars, 2025-11-17→2026-02-17"
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'YahooData':
        """Create from raw dict"""
        indicators = data['indicators']
        return cls(
            price=indicators['price'],
            atr14=indicators['atr14'],
            sma20=indicators['sma20'],
            sma50=indicators['sma50'],
            support=indicators['support'],
            resistance=indicators['resistance'],
            rsi14=indicators['rsi14'],
            summary=data['summary']
        )
    
    def to_prompt(self) -> str:
        """Convert to LLM-friendly prompt string"""
        current_price = self.price
        return f"""
LATEST MARKET DATA FROM YAHOO FINANCE FOR ANALYSIS:
TECHNICAL INDICATORS ({self.summary}):
- Price: ${self.price:.2f}
- SMA20: ${self.sma20:.2f} ({'above' if current_price >= self.sma20 else 'below'})
- SMA50: ${self.sma50:.2f}
- RSI(14): {self.rsi14:.1f} (neutral)
- ATR(14): ${self.atr14:.2f}
- Support: ${self.support:.2f}
- Resistance: ${self.resistance:.2f}
"""


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
    yahoo: YahooData
    timestamp: float  # Unix time from asyncio.get_event_loop().time()
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MarketData':
        """Create from raw state dict"""
        return cls(
            alpaca=AlpacaData.from_dict(data['alpaca']),
            yahoo=YahooData.from_dict(data['yahoo']),
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
    adjusted_order_details: TradingDecision
    risk_evaluation: RiskAssessment
    should_execute: NotRequired[bool]

    # Save to db
    execution_order_id: NotRequired[Optional[str]]

    # Conlfict resolution
    conflict_resolution: NotRequired[Optional[Dict[db_trade_decision, Any]]]