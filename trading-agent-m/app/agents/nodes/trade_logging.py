import httpx
import os
from typing import Dict, Any, List
from app.agents.state import AgentState
import json

TRADING_DB_BASE_URL = os.getenv(
    "TRADING_DB_BASE_URL", "http://localhost:8000/api/v1/trading/decisions"
)


# Update your graph edge to return state
async def node_trade_logging(state: AgentState) -> AgentState:
    """Wrapper to mutate state."""
    # Log trade decision
    print("========================================")
    print("   [📝 Trade Logging] Current Agent State:")
    print("========================================")
    print(json.dumps(state, indent=2))
    print("========================================")
    # Log what's being sent to DB
    db_payload = state.get("conflict_resolution", [])

    # New trade made
    execution_order_id = state.get("execution_order_id")
    if execution_order_id:
        execution_order = {
            "order_id": execution_order_id,
            "symbol": state.get("ticker"),
            "action": state.get("order_details", {}).get("action"),
            # Evaluation details
            "confidence": state.get("adjusted_order_details", {})
            .get("adjusted_trade", {})
            .get("confidence"),
            "risk_evaluation": {
                "risk_per_share": state.get("risk_evaluation", {}).get(
                    "risk_per_share"
                ),
                "reward_per_share": state.get("risk_evaluation", {}).get(
                    "reward_per_share"
                ),
                "actual_rr": state.get("risk_evaluation", {}).get("actual_rr"),
                "total_risk": state.get("risk_evaluation", {}).get("total_risk"),
                "suggested_qty": state.get("risk_evaluation", {}).get("suggested_qty"),
                "near_resistance": state.get("risk_evaluation", {}).get(
                    "near_resistance"
                ),
                "atr_distance": state.get("risk_evaluation", {}).get("atr_distance"),
                "max_risk_5pct": state.get("risk_evaluation", {}).get("max_risk_5pct"),
                "risk_score": state.get("adjusted_order_details", {}).get("risk_score"),
                "risk_status": state.get("adjusted_order_details", {}).get(
                    "risk_status", ""
                ),
            },
            "reasonings": state.get("order_details", {}).get("thesis", ""),
            "risk_adjustments_made": state.get("adjusted_order_details", {}).get(
                "issues", []
            ),
            "market_data": state.get("market_data", {}),  # yahoo, alpaca data
        }
        db_payload.append(execution_order)

    print(f"   [📝 Trade Logging] Sending to DB: {json.dumps(db_payload, indent=2)}")
    # Post to trading DB
    result = await post_order_to_db(db_payload)
    print("   [✅ Trade Logging] DB Response:", result)

    # Store trade decision for DB logging
    # yahoo, alpaca data
    # state["execution_result"]
    # state["order_details"]

    # state['conflict_resolution']
    # [{'order_id': 'f3ff2368-0be7-40d3-8d22-15f3b947290d', 'symbol': 'AAPL', 'action': 'cancelled_orders', 'reasonings': '[Trade Conflict] Cancelled 1 pending order(s) for AAPL due to conflict.'}]

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
