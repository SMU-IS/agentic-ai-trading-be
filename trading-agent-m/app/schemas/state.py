from typing import Dict, Optional, TypedDict

from pydantic import BaseModel


# Redis Stream
class Signal(BaseModel):
    user_id: str
    ticker: str
    signal: dict  # {"sentiment": "bullish", "score": 0.9}
    portfolio: Dict  # {"qty": 10, "avg_price": 150.0} OR {} if not owned
    risk_profile: str  # "aggressive"


class AgentState(TypedDict):
    user_id: str
    ticker: str
    signal: dict
    portfolio: dict
    risk_profile: str

    action: str  # "BUY", "SELL", "IGNORE"
    order_details: Optional[dict]
    should_execute: bool
    reasoning: str
