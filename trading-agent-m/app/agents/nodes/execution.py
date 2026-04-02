import httpx
from typing import Dict, Any
from app.agents.state import AgentState, TradingDecision, RiskAdjResult, RiskAssessment, RiskMetrics
from app.core.config import env_config
import asyncio
import dataclasses

BROKER_URL = env_config.trading_service_url

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


async def node_execute_trade_logic(
    order_details: TradingDecision,
    account_id: str,
) -> Dict[str, Any]:
    """
    Executes approved trades via Broker API POST /trading/orders/bracket.
    """
    ticker      = order_details.ticker
    action      = order_details.action.value.upper()

    if not ticker or not order_details:
        print(f"   [❌ Execute] account={account_id} — no order_details, skipping")
        return {"status": "skipped", "reason": "no_order_details", "account_id": account_id}

    print(f"   [📈 Execute] account={account_id}\n{order_details.to_prompt()}")

    # ── Normalise fields ──────────────────────────────────────────
    order_details.qty          = round(float(order_details.qty), 2)
    order_details.take_profit  = round(float(order_details.take_profit), 2)
    order_details.stop_loss    = round(float(order_details.stop_loss), 2)

    payload = {
        "symbol":            ticker,
        "side":              action.lower(),
        "qty":               order_details.qty,
        "entry_type":        "market",
        "take_profit_price": order_details.take_profit,
        "stop_loss_price":   order_details.stop_loss,
        "time_in_force":     "gtc",
    }

    if hasattr(order_details, "entry_price") and order_details.entry_price is not None:
        order_details.entry_price = round(float(order_details.entry_price), 2)
        payload["entry_type"]  = "limit"
        payload["entry_price"] = order_details.entry_price

    print(f"   [📤 API] POST {BROKER_URL}/orders/bracket | account={account_id}")
    print(f"   [📤 Payload] {payload}")

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(f"{BROKER_URL}/orders/bracket", json=payload, headers={"x-user-id": account_id},)

            if resp.status_code in [200, 201]:
                result = resp.json()
                order_id = result.get("order_id")
                print(f"   [✅ SUCCESS] account={account_id} | order_id={order_id}")
                return {
                    "status":       "executed",
                    "order_id":     order_id,
                    "account_id":   account_id,
                    "symbol":       ticker,
                    "side":         action,
                    "submitted_at": result.get("submitted_at"),
                    "full_response": result,
                }

            error_msg = resp.json().get("detail", "Unknown error")
            print(f"   [❌ FAILED {resp.status_code}] account={account_id} | {error_msg}")
            return {
                "status":     "failed",
                "account_id": account_id,
                "error":      error_msg,
                "symbol":     ticker,
                "payload":    payload,
            }

        except httpx.TimeoutException:
            print(f"   [❌ TIMEOUT] account={account_id}")
            return {"status": "timeout", "account_id": account_id}
        except Exception as e:
            print(f"   [❌ ERROR] account={account_id} | {e}")
            return {"status": "error", "account_id": account_id, "error": str(e)}


async def node_execute_trade(state: AgentState) -> AgentState:
    order_details_base: TradingDecision = state.get("order_details")
    market_data_raw                     = state.get("market_data", {})
    signal_id                           = state.get("signal_id", "")

    order_list: list[RiskAdjResult] = state.get("order_list", [])

    executable = [o for o in order_list if o["should_execute"]]
    skipped    = [o for o in order_list if not o["should_execute"]]

    if not executable:
        print("   [⏭️ Execute] No executable orders — all blocked by conflict resolution")
        return {"execution_results": [
            {"status": "skipped", "user_id": o.user_id, "profile": o.profile.value, "reason": "conflict_resolution"}
            for o in skipped
        ]}

    # ── Execute all users concurrently ────────────────────────────
    raw_results = await asyncio.gather(
        *[node_execute_trade_logic(o["adjusted_order_details"], o["user_id"]) for o in executable]
    )

    # ── Enrich each result ────────────────────────────────────────
    def _enrich(raw: dict, order_item: RiskAdjResult) -> dict:
        assessment: RiskAssessment = order_item.get("risk_evaluation")
        metrics:    RiskMetrics    = assessment.metrics if assessment else None
        return {
            **raw,
            "profile":    order_item.get("profile").value,
            "user_id":    order_item.get("user_id"),
            "confidence": order_details_base.confidence if order_details_base else None,
            "reasonings": order_details_base.thesis     if order_details_base else None,
            "signal_id":  signal_id,
            "risk_evaluation": {
                "risk_per_share":   metrics.risk_per_share   if metrics else None,
                "reward_per_share": metrics.reward_per_share if metrics else None,
                "actual_rr":        metrics.actual_rr        if metrics else None,
                "total_risk":       metrics.total_risk       if metrics else None,
                "suggested_qty":    metrics.suggested_qty    if metrics else None,
                "near_resistance":  metrics.near_resistance  if metrics else None,
                "atr_distance":     metrics.atr_distance     if metrics else None,
                "max_risk_5pct":    metrics.max_risk_5pct    if metrics else None,
                "risk_score":       metrics.risk_score       if metrics else None,
                "risk_status":      assessment.risk_status   if assessment else None,
            },
            "risk_adjustments_made": assessment.issues if assessment else [],
            "market_data":           to_serializable(market_data_raw),
        }

    enriched = [_enrich(raw, order_item) for raw, order_item in zip(raw_results, executable)]
    enriched += [
        {"status": "skipped", "user_id": o["user_id"], "profile": o["profile"].value, "reason": "conflict_resolution"}
        for o in skipped
    ]

    executed = sum(1 for r in enriched if r.get("status") == "executed")
    print(f"   [🚀 Execute] {executed}/{len(enriched)} orders placed")

    return {"execution_results": enriched}
