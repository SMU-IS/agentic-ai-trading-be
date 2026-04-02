import httpx
import asyncio
import dataclasses
from typing import Dict, Any, List
from app.agents.state import AgentState
from app.core.config import env_config
from app.services.telegram_service import post_order_to_telegram

TRADING_DB_BASE_URL = f"{env_config.trading_service_url}/decisions"


def to_serializable(obj: Any) -> Any:
    """Convert dataclasses/enums to JSON-serializable format."""
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    elif hasattr(obj, "value"):  # Enums
        return obj.value
    elif isinstance(obj, dict):
        return {k: to_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [to_serializable(item) for item in obj]
    return obj


async def node_trade_logging(redis_service, state: AgentState) -> AgentState:
    conflict_resolutions = [item for sublist in state.get("all_conflict_resolutions", []) for item in sublist]
    execution_results    = state.get("execution_results", [])
    notification_order_id= []
    db_payload_executions = []
    for order in execution_results:
        if order.get("status") != "executed":
            continue
        # Crafting notification
        order_id = order.get("order_id")
        user_id  = order.get("user_id")
        if not order_id:
            print(f"   [⚠️  Trade Logging] Skipping notification — missing order_id for user={user_id}")
            continue
        notification_order_id.append({"order_id": order_id, "user_id": user_id})
        # Setting payload by order
        risk_eval = order.get("risk_evaluation", {})
        db_payload_executions.append({
            "order_id":   order_id,
            "symbol":     order.get("symbol"),
            "action":     order.get("side"),
            "confidence": order.get("confidence"),
            "risk_evaluation": {
                "risk_per_share":   risk_eval.get("risk_per_share"),
                "reward_per_share": risk_eval.get("reward_per_share"),
                "actual_rr":        risk_eval.get("actual_rr"),
                "total_risk":       risk_eval.get("total_risk"),
                "suggested_qty":    risk_eval.get("suggested_qty"),
                "near_resistance":  risk_eval.get("near_resistance"),
                "atr_distance":     risk_eval.get("atr_distance"),
                "max_risk_5pct":    risk_eval.get("max_risk_5pct"),
                "risk_score":       risk_eval.get("risk_score"),
                "risk_status":      risk_eval.get("risk_status"),
            },
            "reasonings":            order.get("reasonings"),
            "risk_adjustments_made": order.get("risk_adjustments_made", []),
            "market_data":           to_serializable(order.get("market_data", {})),
            "signal_id":             state.get("signal_id"),
            "user_id":               user_id,
            "profile":               order.get("profile")
        })

    all_payload = conflict_resolutions + db_payload_executions
    if all_payload:
        result = await post_order_to_db(all_payload)
        print(f"   [✅ Trade Logging] DB upload complete | success={result.get('success')} failed={result.get('failed')}")

    if db_payload_executions:
        print(f"   [📬 Telegram] Posting {len(db_payload_executions)} executed order(s) to Telegram")
        await asyncio.gather(*[post_order_to_telegram(o) for o in db_payload_executions])
    
    if notification_order_id:
        news_id = state["signal_data"].news_id
        ticker  = state["signal_data"].ticker
        print(f"   [📢 Notify] Publishing {len(notification_order_id)} trade notification(s) | {ticker} | news={news_id}")
        await asyncio.gather(
            redis_service.publish_trade_noti(notification_order_id),
            redis_service.publish_order_timestamp(news_id, ticker),
            redis_service.pipeline_counter(),
        )
        print(f"   [✅ Notify] Notifications dispatched for {len(notification_order_id)} order(s)")

async def post_order_to_db(data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Post orders to trading database."""
    print(f"   [📝 Trade Logging] Sending to DB: {[x['order_id'] for x in data]}")
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{TRADING_DB_BASE_URL}/orders",
                json=data,
                headers={"Content-Type": "application/json"},
            )

            if resp.status_code in [200, 201]:
                return resp.json()

            print(f"   [❌ HTTP {resp.status_code}] {resp.text}")
            return {"error": f"HTTP {resp.status_code}", "response": resp.text}

        except httpx.RequestError as e:
            print(f"   [❌ Network Error] {e}")
            return {"error": "network_error", "details": str(e)}
        except Exception as e:
            print(f"   [❌ Trade Logging] {e}")
            return {"error": "unexpected_error", "details": str(e)}
