import httpx
import os
from typing import Dict, Any, List
from app.agents.state import AgentState, MarketData, RiskAssessment, RiskMetrics, TradingDecision
import json
import dataclasses

TRADING_DB_BASE_URL = os.getenv(
    "TRADING_DB_BASE_URL", "http://localhost:8000/api/v1/trading/decisions"
)

def to_serializable(obj: Any) -> Any:
    """Convert dataclasses/enums to JSON-serializable format"""
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    elif hasattr(obj, 'value'):  # Enums
        return obj.value
    elif isinstance(obj, dict):
        return {k: to_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [to_serializable(item) for item in obj]
    return obj

# Update your graph edge to return state
async def node_trade_logging(state: AgentState) -> AgentState:
    """Wrapper to mutate state."""
    # [DEBUG] Log trade decision
    # print("========================================")
    # print("   [📝 Trade Logging] Current Agent State:")
    # print("========================================")
    
    # # ✅ Convert state to serializable before json.dumps
    # serializable_state = to_serializable(state)
    # print(json.dumps(serializable_state, indent=2, default=str))
    # print("========================================")
    
    # Log what's being sent to DB
    db_payload = state.get("conflict_resolution", [])
    
    order_details: TradingDecision = state.get("order_details")
    risk_assessment: RiskAssessment = state.get("risk_evaluation")
    risk_metric: RiskMetrics = risk_assessment.metrics if risk_assessment else None
    
    market_data_raw = state.get("market_data", {})
    execution_order_id = state.get("execution_order_id")

    print(f"   [📝 Trade Logging] Prepared DB Payload: {execution_order_id}")
    if execution_order_id:
        # ✅ Convert ALL objects to dicts
        execution_order = {
            "order_id": execution_order_id,
            "symbol": order_details.ticker,
            "action": order_details.action.value,
            "confidence": order_details.confidence,
            "risk_evaluation": {
                "risk_per_share": risk_metric.risk_per_share,
                "reward_per_share": risk_metric.reward_per_share,
                "actual_rr": risk_metric.actual_rr,
                "total_risk": risk_metric.total_risk,
                "suggested_qty": risk_metric.suggested_qty,
                "near_resistance": risk_metric.near_resistance,
                "atr_distance": risk_metric.atr_distance,
                "max_risk_5pct": risk_metric.max_risk_5pct,
                "risk_score": risk_metric.risk_score,
                "risk_status": risk_assessment.risk_status,  # Fixed: from assessment
            },
            "reasonings": order_details.thesis,
            "risk_adjustments_made": risk_assessment.issues,
            "market_data": to_serializable(market_data_raw),  # ✅ Converts SignalData
            "signal_id": state.get("signal_id"),
        }
        db_payload.append(execution_order)
    
    # ✅ Serialize db_payload safely
    print(f"   [📝 Trade Logging] Sending to DB: {json.dumps(to_serializable(db_payload), indent=2, default=str)}")
    
    # Post to trading DB
    result = await post_order_to_db(db_payload)
    print("   [✅ Trade Logging] DB Response:", result)

    return state

async def post_order_to_db(data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Post orders to trading database."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # Fixed: Use json= (not data=) and correct endpoint
            resp = await client.post(
                f"{TRADING_DB_BASE_URL}/orders",  # Fixed endpoint
                json=data,  # ✅ json= serializes List[Dict] correctly
                headers={"Content-Type": "application/json"},
            )

            if resp.status_code in [200, 201]:
                return resp.json()
            else:
                print(f"❌ HTTP {resp.status_code}: {resp.text}")
                return {"error": f"HTTP {resp.status_code}", "response": resp.text}

        except httpx.RequestError as e:
            print(f"  [❌ Network Error] {e}")
            return {"error": "Network error", "details": str(e)}
        except Exception as e:
            print(f"  [❌ Trading DB] {e}")
            return {"error": "Unexpected error", "details": str(e)}
