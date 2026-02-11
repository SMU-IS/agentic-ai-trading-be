from pydantic import BaseModel
from typing import Dict, List, Optional, TypedDict, Any
from typing_extensions import NotRequired


# Redis Stream
class Signal(BaseModel):
    user_id: str
    ticker: str
    signal: dict  # {"sentiment": "bullish", "score": 0.9}
    portfolio: Dict  # {"qty": 10, "avg_price": 150.0} OR {} if not owned
    risk_profile: str  # "aggressive"


class db_trade_decision(TypedDict):
    order_id: str
    symbol: str
    action: str
    reasonings: str


class risk_evaluation_result(TypedDict):
    adjusted_order_details: Optional[Dict[str, Any]]
    risk_evaluation: Optional[Dict[str, Any]]
    confidence: Optional[float]
    risk_score: Optional[float]


class AgentState(TypedDict):
    # Required input fields
    user_id: str
    ticker: str
    signal: dict
    portfolio: dict
    risk_profile: str

    # Optional for lookup_context
    query_vector: NotRequired[Optional[List[float]]]
    historical_context: NotRequired[List[Dict[str, Any]]]

    # Market data from node_fetch_market_data
    market_data: NotRequired[Optional[Dict[str, Any]]]

    # Output from reasoning
    action: NotRequired[str]  # "BUY", "SELL", "HOLD", "IGNORE"
    order_details: NotRequired[Optional[Dict[str, Any]]]

    # Conditional execution
    should_execute: NotRequired[bool]
    has_trade_opportunity: NotRequired[bool]

    # Output from risk adjustment
    adjusted_order_details: NotRequired[Optional[Dict[str, Any]]]
    risk_evaluation: NotRequired[Optional[Dict[str, Any]]]

    # Save to db
    execution_order_id: NotRequired[Optional[str]]
    trade_decision: NotRequired[Optional[Dict[str, Any]]]

    # Conlfict resolution
    conflict_resolution: NotRequired[Optional[Dict[db_trade_decision, Any]]]
