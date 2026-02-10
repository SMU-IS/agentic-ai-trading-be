from app.agents.state import AgentState, db_trade_decision
from typing import Dict, Any, List
import httpx

import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL", "http://localhost:8000/api/v1/trading")

# Tunables for your bot
MAX_RISK_PCT = 0.01  # 1% of equity per trade
MIN_CONFIDENCE = 0.55  # Below this = HOLD
MAX_NOTIONAL_PCT = 0.20  # Max 20% of equity in any one trade


async def node_risk_adjust_trade_logic(state: AgentState) -> AgentState:

    order_details = state.get("order_details", {})
    action = order_details.get("action", "").upper()

    market_data = state.get("market_data", {})
    yahoo_data = market_data.get("yahoo", {})

    print("   [🛡️ Risk Layer] Evaluating trade risk...")
    account_fetch_task = fetch_buying_power()
    account_bp = await asyncio.gather(account_fetch_task)
    print(f"   [💰 Buying Power] {account_bp[0]}")

    # Risk evaluation metrics
    evaluation_result = risk_evaluation_metrics(
        order_details, yahoo_data, account_bp[0]
    )
    print_risk_evaluation(evaluation_result)

    state["order_details"] = evaluation_result.get("adjusted_trade", order_details)
    order_details = state.get("order_details", {})

    conflict_resolve_task = resolve_conflicting_position(
        order_details.get("ticker"), action.lower(), order_details.get("qty", 0)
    )
    conflict_resolve_summary = await asyncio.gather(conflict_resolve_task)

    if conflict_resolve_summary[0].get("has_conflict", False):
        state["conflict_resolution"] = conflict_resolve_summary[0].get(
            "conflict_resolution", {}
        )

        print(f"   [🛡️ Risk Layer] Conflict Resolution: {state['conflict_resolution']}")

    # If no conflicting order or position, proceed with original order
    print(
        "   [🛡️ Risk Layer] Should Execute? ",
        not conflict_resolve_summary[0].get("has_conflict", False),
    )

    state["should_execute"] = not conflict_resolve_summary[0].get("has_conflict", False)
    state["adjusted_order_details"] = evaluation_result
    state["risk_evaluation"] = evaluation_result.get("metrics", {})
    return state


async def node_risk_adjust_trade(state: AgentState) -> AgentState:
    await node_risk_adjust_trade_logic(state)
    return state


async def fetch_buying_power() -> Dict[str, Any]:
    """Fetch Yahoo historical + key indicators for LLM prompts."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{ALPACA_BASE_URL}/account")
            if resp.status_code != 200:
                return {"error": "Yahoo unavailable"}

            data = resp.json()

            if "non_marginable_buying_power" in data:
                return data.get("non_marginable_buying_power", 0)

            return {"error": "No valid buying power"}

        except Exception as e:
            return {"error": str(e)}


async def resolve_conflicting_position(
    symbol: str,
    side: str,
    qty: float,
) -> Dict[str, Any]:
    """
    Determine if a new order conflicts with existing position.

    Returns:
    {
      "has_conflict": bool,
      "current_side": "long" | "short" | "flat",
      "current_qty": float,
      "required_close_qty": float,   # how much must be closed first
      "effective_new_side": "long" | "short" | "flat",
      "effective_new_qty": float     # remaining qty after close
    }
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{ALPACA_BASE_URL}/orders/resolve-conflicts",
                json={
                    "symbol": symbol,
                    "intended_side": side,
                    "intended_qty": qty,
                    "auto_resolve": True,
                },
            )

            # Extract key info you want
            result = resp.json()
            print("[🛡️ RISK LAYER RESULT]", result)
            print()
            # 1. CONFLICT STATUS
            has_conflict = result["conflicts_detected"]["has_conflict"]
            print(f"🎯 CONFLICT: {has_conflict}")

            # 2. CURRENT POSITION (before resolution)
            if "current_position" in result["conflicts_detected"]:
                current_pos = result["conflicts_detected"]["current_position"]
                print("🛡️ RISK LAYER")
                print(f"  📊 Current qty:     {current_pos['qty']}")
                print(f"  🔄 Current side:    {current_pos['side']}")
                print(f"  💰 Avg entry:       ${current_pos['avg_entry_price']:.2f}")
                print(f"  📈 Market value:    ${current_pos['market_value']:.2f}")
                print(f"  🎯 Unrealized P&L:  ${current_pos['unrealized_pl']:.2f}")
                print()

            # 3. ACTIONS TAKEN (what was resolved)
            print("📋 ALL ACTIONS SUMMARY")
            actions_summary = handle_actions_taken(result)
            print(actions_summary)
            conflict_resolution: List[db_trade_decision] = []

            for act in actions_summary:
                action_type = act["action"]

                if action_type == "closed_position":
                    vars_dict = db_trade_decision(
                        order_id=act["order_id"],
                        symbol=symbol,
                        action=action_type,
                        reasonings=f"[Trade Conflict] Closed {act['qty_closed']:.1f} share(s) of {symbol}",
                    )
                elif action_type == "cancelled_orders":
                    vars_dict = db_trade_decision(
                        order_id="".join(act["order_ids"][:2]),
                        symbol=symbol,
                        action=action_type,
                        reasonings=f"[Trade Conflict] Cancelled {act['count']} pending order(s) for {symbol}",
                    )

                conflict_resolution.append(vars_dict)

            # 🖥️ CLEAN OUTPUT
            print("⚡ ACTIONS TAKEN")
            for i, act in enumerate(actions_summary, 1):
                print(f"  {i}. ✅ {act['action'].replace('_', ' ').title()}")
                print(f"     Status: {act['status']}")

                if act["action"] == "closed_position":
                    print(f"     Qty: {act['qty']:.1f} | Side: {act['side']}")
                    print(f"     Order: {act['order_id']}")
                    if act.get("reason"):
                        print(f"     Reason: {act['reason']}")
                elif act["action"] == "cancelled_orders":
                    print(f"     Count: {act['count']} orders")
                    print(f"     Orders: {', '.join(act['order_ids'][:2])}")
                    if act["details"]:
                        print(
                            f"     Details: {act['details']['qty']} {act['details']['side']} {act['details']['order_type']}"
                        )
                    if act.get("reason"):
                        print(f"     Reason: {act['reason']}")
                print()

            # SUMMARY OBJECT (for your agent)
            summary = {
                "status": result["status"],
                "symbol": result["symbol"],
                "has_conflict": has_conflict,
                "current_position": result["conflicts_detected"].get(
                    "current_position", {}
                ),
                "actions_taken": actions_summary,
                "conflict_resolution": conflict_resolution,
            }

            return summary
        except Exception as e:
            return {"error": str(e)}


def handle_actions_taken(result):
    actions_summary = []
    for action in result["actions_taken"]:
        if action["status"] == "success":
            if action["action"] == "closed_position":
                # Find matching reason from actions_required
                reason = ""
                for req_action in result["conflicts_detected"].get(
                    "actions_required", []
                ):
                    if req_action["action"] == "close_position":
                        reason = req_action.get("reason", "")
                        break

                actions_summary.append(
                    {
                        "action": action["action"],
                        "status": action["status"],
                        "qty": action["qty_closed"],
                        "side": "SELL" if action["qty_closed"] > 0 else "BUY",
                        "order_id": action["order_id"],
                        "reason": reason,
                        "symbol": action.get("symbol", result["symbol"]),
                    }
                )
            elif action["action"] == "cancelled_orders":
                # Find matching reason from actions_required
                reason = ""
                for req_action in result["conflicts_detected"].get(
                    "actions_required", []
                ):
                    if (
                        req_action["action"] == "cancel_orders"
                        and req_action.get("order_ids") == action["order_ids"]
                    ):
                        reason = req_action.get("reason", "")
                        break

                # Find matching order details from conflicting_orders
                order_details = {}
                for conflict_order in result["conflicts_detected"].get(
                    "conflicting_orders", []
                ):
                    if conflict_order["order_id"] in action["order_ids"]:
                        order_details = {
                            "qty": conflict_order["qty"],
                            "side": conflict_order["side"],
                            "order_type": conflict_order["order_type"],
                            "status": conflict_order["status"],
                        }
                        break

                actions_summary.append(
                    {
                        "action": action["action"],
                        "status": action["status"],
                        "count": action["count"],
                        "order_ids": action["order_ids"],
                        "details": order_details,
                        "reason": reason,
                        "symbol": result["symbol"],
                    }
                )
            else:
                actions_summary.append(
                    {
                        "action": action["action"],
                        "status": action["status"],
                        "details": action,
                    }
                )
    return actions_summary


def risk_evaluation_metrics(trade_decision, yahoo_data, account_bp) -> Dict[str, Any]:
    trade = trade_decision
    yahoo = yahoo_data
    account_bp = float(account_bp)  # Ensure float

    current_price = float(trade["current_stock_price"])
    atr = float(yahoo["indicators"]["atr14"])
    resistance = float(yahoo["indicators"]["resistance"])
    support = float(yahoo["indicators"]["support"])
    entry_price = float(trade["entry_price"])

    # 1. 🚨 DIRECTIONAL VALIDATION & AUTO-FIX
    issues = []
    adjusted_trade = trade.copy()

    price_diff_pct = abs(entry_price - current_price) / current_price * 100

    if price_diff_pct > 1.0:  # >2% deviation = too far
        original_entry = entry_price
        entry_price = current_price  # Snap to current
        issues.append(
            {
                "field": "entry_price",
                "reason": "Entry price deviates >2% from current market price.",
                "adjustment": f"Moved from ${original_entry:.2f} ({price_diff_pct:.1f}%) → ${current_price:.2f} (current market)",
            }
        )

    adjusted_trade["entry_price"] = entry_price

    if trade["action"] == "BUY":
        # BUY: SL must be BELOW entry, TP must be ABOVE entry
        original_sl = trade.get("stop_loss")
        original_tp = trade.get("take_profit")

        new_sl = max(support, entry_price - atr)
        new_tp = min(resistance, entry_price + (atr * 2))

        adjusted_trade["stop_loss"] = new_sl
        adjusted_trade["take_profit"] = new_tp

        if original_sl is not None and new_sl != original_sl:
            issues.append(
                {
                    "field": "stop_loss",
                    "reason": "Stop loss for BUY should be below entry.",
                    "adjustment": f"Moved SL from {original_sl} to {new_sl} to sit below entry and near support 1×ATR.",
                }
            )
        if original_tp is not None and new_tp != original_tp:
            issues.append(
                {
                    "field": "take_profit",
                    "reason": "Take profit for BUY should be above entry.",
                    "adjustment": f"Moved TP from {original_tp} to {new_tp} to sit above entry and near resistance 2×ATR.",
                }
            )

    elif trade["action"] == "SELL":
        # SELL: SL must be ABOVE entry, TP must be BELOW entry
        original_sl = trade.get("stop_loss")
        original_tp = trade.get("take_profit")

        new_tp = max(support, entry_price - (atr * 2))
        new_sl = min(resistance, entry_price + atr)

        adjusted_trade["take_profit"] = new_tp
        adjusted_trade["stop_loss"] = new_sl

        if original_sl is not None and new_sl != original_sl:
            issues.append(
                {
                    "field": "stop_loss",
                    "reason": "Stop loss for SELL should be above entry.",
                    "adjustment": f"Moved SL from {original_sl} to {new_sl} to sit above entry and below resistance 1×ATR.",
                }
            )
        if original_tp is not None and new_tp != original_tp:
            issues.append(
                {
                    "field": "take_profit",
                    "reason": "Take profit for SELL should be below entry.",
                    "adjustment": f"Moved TP from {original_tp} to {new_tp} to sit below entry and near support 2×ATR.",
                }
            )

    # 2. 📊 RISK CALCULATIONS - ALL FLOATS
    risk_per_share = abs(
        float(adjusted_trade["entry_price"]) - float(adjusted_trade["stop_loss"])
    )
    reward_per_share = abs(
        float(adjusted_trade["take_profit"]) - float(adjusted_trade["entry_price"])
    )
    actual_rr = reward_per_share / risk_per_share

    max_risk_pct = 0.05 if float(trade["confidence"]) >= 0.8 else 0.03
    max_risk_dollars = account_bp * max_risk_pct
    suggested_qty = max_risk_dollars // current_price
    adjusted_trade["qty"] = suggested_qty  # Use suggested qty for 5% risk

    total_risk_dollars = suggested_qty * risk_per_share  # ✅ Now float * float
    risk_pct_account = (total_risk_dollars / account_bp) * 100

    # 3. 🎯 SCORING
    risk_score = float(trade["confidence"])
    near_resistance = abs(current_price - resistance) < atr
    risk_score += 0.2 if near_resistance else 0.0
    risk_score += 0.1 if atr > 5.0 else 0.0
    risk_score += 0.15 if actual_rr >= 1.5 else -0.1
    risk_score += 0.1 if risk_pct_account >= 2.0 else 0.0

    return {
        "risk_status": "APPROVED" if risk_score >= 0.9 else "REVIEW",
        "risk_score": round(min(risk_score, 1.5), 2),
        "adjusted_trade": adjusted_trade,
        "metrics": {
            "risk_score": round(min(risk_score, 1.5), 2),
            "risk_per_share": f"${risk_per_share:.2f}",
            "reward_per_share": f"${reward_per_share:.2f}",
            "actual_rr": f"{actual_rr:.1f}:1",
            "total_risk": f"${total_risk_dollars:.0f} ({risk_pct_account:.1f}%)",
            "suggested_qty": f"{suggested_qty:.0f}",
            "near_resistance": near_resistance,
            "atr_distance": f"{atr:.1f}",
            "max_risk_5pct": f"${max_risk_dollars:.0f}",
        },
        "issues": issues,
    }


## Printing helper
def print_risk_evaluation(evaluation_result):
    """Pretty print risk evaluation results"""

    result = evaluation_result
    print(result)
    trade = result["adjusted_trade"]
    metrics = result["metrics"]

    # Header
    print("\n" + "=" * 60)
    print("🎯 RISK EVALUATION REPORT")
    print("=" * 60)

    # Status
    status_emoji = "✅" if result["risk_status"] == "APPROVED" else "⚠️"
    print(f"\n{status_emoji} STATUS: {result['risk_status']}")
    print(f"📊 RISK SCORE: {result['risk_score']:.2f}/1.50")

    # Trade Details
    print("\n📋 TRADE SETUP")
    print(f"  Action:        {trade['action']}")
    print(f"  Symbol:        {trade.get('ticker', 'N/A')}")
    print(f"  Confidence:    {trade['confidence'] * 100:.0f}%")
    print(f"  Entry:         ${trade['entry_price']:.2f}")
    print(f"  Stop Loss:     ${trade['stop_loss']:.2f}")
    print(f"  Take Profit:   ${trade['take_profit']:.2f}")
    print(f"  Quantity:      {trade['qty']} shares")

    # Risk Metrics
    print("\n💰 RISK METRICS")
    print(f"  Risk/Share:    {metrics['risk_per_share']}")
    print(f"  Reward/Share:  {metrics['reward_per_share']}")
    print(f"  Actual R:R:    {metrics['actual_rr']}")
    print(f"  Total Risk:    {metrics['total_risk']}")

    # Position Sizing
    print("\n📐 POSITION SIZING")
    print(f"  Current Qty:   {trade['qty']} shares")
    print(f"  Suggested Qty: {metrics['suggested_qty']} shares (5% risk)")
    print(f"  Max Risk (5%): {metrics['max_risk_5pct']}")

    # Technical Context
    print("\n📈 TECHNICAL CONTEXT")
    print(f"  Near Resistance: {'Yes ✅' if metrics['near_resistance'] else 'No'}")
    print(f"  ATR Distance:    {metrics['atr_distance']}")

    # Thesis
    if "thesis" in trade:
        print("\n💡 THESIS")
        # Wrap thesis text
        thesis = trade["thesis"]
        max_width = 56
        words = thesis.split()
        lines = []
        current_line = "  "

        for word in words:
            if len(current_line) + len(word) + 1 <= max_width:
                current_line += word + " "
            else:
                lines.append(current_line.rstrip())
                current_line = "  " + word + " "
        if current_line.strip():
            lines.append(current_line.rstrip())

        print("\n".join(lines))

    # Issues/Warnings
    if result["issues"]:
        print("\n⚠️ ADJUSTMENTS MADE")
        for issue in result["issues"]:
            print(f"  • {issue}")
    else:
        print("\n✅ NO ADJUSTMENTS NEEDED")

    print("\n" + "=" * 60 + "\n")
