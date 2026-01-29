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
    should_execute: NotRequired[bool]
    reasoning: NotRequired[str]
