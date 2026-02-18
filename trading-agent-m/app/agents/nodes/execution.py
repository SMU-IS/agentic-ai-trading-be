import httpx
import os
from dotenv import load_dotenv
from typing import Dict, Any
from app.agents.state import AgentState, TradingDecision

# Load env vars
load_dotenv()
BROKER_URL = os.getenv("BROKER_URL", "http://localhost:8000/api/v1")


async def node_execute_trade_logic(state: AgentState) -> Dict[str, Any]:
    """
    Executes approved trades via Broker API POST /trading/orders/bracket.
    """
    order_details: TradingDecision = state.get("adjusted_order_details", {})
    ticker = order_details.ticker
    action = order_details.action.value.upper()

    if not ticker or not order_details:
        print("   [❌ Execute] No order_details - skipping")
        return {"execution_result": {"status": "skipped", "reason": "no_order_details"}}

    print(f"   [📈 Market Access] Executing \n{order_details.to_prompt()}")

    # Handle rounding and type conversions
    order_details.qty = round(float(order_details.qty), 2)
    order_details.take_profit = round(float(order_details.take_profit), 2)
    order_details.stop_loss = round(float(order_details.stop_loss), 2)

    # Build exact API payload
    payload = {
        "symbol": ticker,
        "side": action.lower(),  # "buy" or "sell"
        "qty": order_details.qty,
        "entry_type": "market",  # or "limit" if entry_price provided
        "take_profit_price": order_details.take_profit,
        "stop_loss_price": order_details.stop_loss,
        "time_in_force": "day",  # or state.get("time_in_force", "day")
    }

    if hasattr(order_details, "entry_price") and order_details.entry_price is not None:
        order_details.entry_price = round(float(order_details.entry_price), 2)
        payload["entry_type"] = "limit"
        payload["entry_price"] = order_details.entry_price

    print(f"   [📤 API] POST {BROKER_URL}/trading/orders/bracket")
    print(f"   [📤 Payload] {payload}")

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{BROKER_URL}/trading/orders/bracket", json=payload
            )

            if resp.status_code in [200, 201]:
                result = resp.json()
                print(f"   [✅ SUCCESS] Order ID: {result.get('order_id')}")
                return {
                    "execution_result": {
                        "status": "success",
                        "order_id": result.get("order_id"),
                        "symbol": ticker,
                        "side": action,
                        "submitted_at": result.get("submitted_at"),
                        "full_response": result,
                    }
                }
            else:
                error_msg = resp.json().get("detail", "Unknown error")
                print(f"   [❌ FAILED {resp.status_code}] {error_msg}")
                return {
                    "execution_result": {
                        "status": "failed",
                        "error": error_msg,
                        "symbol": ticker,
                        "payload": payload,  # For debugging
                    }
                }

        except httpx.TimeoutException:
            print("   [❌ TIMEOUT] Broker API timeout")
            return {"execution_result": {"status": "timeout"}}
        except Exception as e:
            print(f"   [❌ ERROR] {str(e)}")
            return {"execution_result": {"status": "error", "error": str(e)}}


# Update your graph edge to return state
async def node_execute_trade(state: AgentState) -> AgentState:
    """Wrapper to mutate state."""
    print("   [🚀 Execute Trade] Starting trade execution node...")
    execution_result = await node_execute_trade_logic(state)
    # print(f"   [🧾 Execution Result] {execution_result}")
    state["execution_order_id"] = execution_result.get("execution_result", {}).get("order_id", None)
    print(f"   [✅ Execution Result] Order ID set in state: {state['execution_order_id']}")
    return state
