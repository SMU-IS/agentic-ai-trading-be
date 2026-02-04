import httpx
import asyncio
import os
from dotenv import load_dotenv
from typing import Dict, Any
from app.agents.state import AgentState

# Load env vars
load_dotenv()
BROKER_URL = os.getenv("BROKER_URL", "http://localhost:8000/api/v1")

async def node_execute_trade_logic(state: AgentState) -> Dict[str, Any]:
    """
    Executes approved trades via Broker API POST /trading/orders/bracket.
    """
    order_details = state.get("order_details", {})
    ticker = order_details.get("ticker")
    action = order_details.get("action", "").upper()
    
    if not ticker or not order_details:
        print("   [❌ Execute] No order_details - skipping")
        return {"execution_result": {"status": "skipped", "reason": "no_order_details"}}
    
    print(f"!!! [🤝🏻 Market Access] Executing {action} {order_details}")
    
    # Handle rounding and type conversions
    payload_qty = round(float(order_details.get("qty", 0)), 2)
    payload_take_profit = round(float(order_details.get("take_profit", 0)), 2)
    payload_stop_loss = round(float(order_details.get("stop_loss", 0)), 2)

    order_details["qty"] = payload_qty
    order_details["take_profit"] = payload_take_profit
    order_details["stop_loss"] = payload_stop_loss
    
    # Build exact API payload
    payload = {
        "symbol": ticker,
        "side": action.lower(),  # "buy" or "sell"
        "qty": payload_qty,
        "entry_type": "market",  # or "limit" if entry_price provided
        "take_profit_price": payload_take_profit,
        "stop_loss_price": payload_stop_loss,
        "time_in_force": "day"  # or state.get("time_in_force", "day")
    }
    
    if "entry_price" in order_details:
        payload_entry_price = round(float(order_details["entry_price"]), 2)
        order_details["entry_price"] = payload_entry_price
        
        payload["entry_type"] = "limit"
        payload["entry_price"] = payload_entry_price
    
    print(f"   [📤 API] POST {BROKER_URL}/trading/orders/bracket")
    print(f"   [📤 Payload] {payload}")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{BROKER_URL}/trading/orders/bracket",
                json=payload
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
                        "full_response": result
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
                        "payload": payload  # For debugging
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
    execution_result = await node_execute_trade_logic(state)
    state["execution_result"] = execution_result
    print(f"   [🧾 Execution Result] {execution_result}")
    return state
