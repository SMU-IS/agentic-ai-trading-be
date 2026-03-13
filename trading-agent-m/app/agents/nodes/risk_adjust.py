import dataclasses
from app.agents.state import AgentState, RiskAssessment, RiskMetrics, TradeAction, YahooData, closed_position, db_trade_decision, TradingDecision, MarketData
from typing import Dict, Any, List
import httpx
import asyncio
from app.core.config import env_config
ALPACA_BASE_URL = env_config.trading_service_url

# Tunables for your bot
MAX_RISK_PCT = 0.01  # 1% of equity per trade
MIN_CONFIDENCE = 0.55  # Below this = HOLD
MAX_NOTIONAL_PCT = 0.20  # Max 20% of equity in any one trade


async def node_risk_adjust_trade_logic(state: AgentState) -> AgentState:
    order_details: TradingDecision = state.get("order_details")

    market_data: MarketData = state.get("market_data", MarketData(
        alpaca=None,
        yahoo=None,
        timestamp=0.0
    ))

    yahoo_data = market_data.yahoo if market_data.yahoo else {}

    print("   [🛡️ Risk Layer] Evaluating trade risk...")
    account_fetch_task = fetch_buying_power()
    account_bp = await asyncio.gather(account_fetch_task)
    
    print(f"   [💰 Buying Power] {account_bp[0]}")

    # Risk evaluation metrics
    evaluation_result: RiskAssessment = risk_evaluation_metrics(
        order_details, yahoo_data, account_bp[0]
    )
    print(f"   [🛡️ Risk Layer] Risk score {evaluation_result.risk_score}/1.50")
    # print_risk_evaluation(evaluation_result)
    order_details = evaluation_result.adjusted_trade
    
    conflict_resolve_summary = await resolve_conflicting_position(
        order_details.ticker, order_details.action.value, order_details.qty, state.get("signal_id", "")
    )
    # [DEBUG]: Print conflict resolution summary
    print(f"   [🛡️ Risk Layer] Conflict Resolution status: {conflict_resolve_summary.get('status', 'No Conflict Detected')}")
    # print(conflict_resolve_summary)
    should_execute = True
    if conflict_resolve_summary.get("has_conflict", False):
        state["conflict_resolution"] = conflict_resolve_summary.get(
            "conflict_resolution", {}
        )
        # print(f"   [🛡️ Risk Layer] Conflict Resolution: {state['conflict_resolution']}")

        # If no current position, we want to execute a new order
        if conflict_resolve_summary.get("current_position", None) is not None:
            should_execute = False
            
    # should_execute = not conflict_resolve_summary.get("has_conflict", False) and evaluation_result.risk_status == "APPROVED"

    print ("   [🛡️ Risk Layer] Should Execute? ", should_execute)
    state["should_execute"] = should_execute
    state["adjusted_order_details"] = evaluation_result.adjusted_trade
    state["risk_evaluation"] = evaluation_result
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
    signal_id: str = ""
) -> Dict[str, Any]:
    """
    Determine if a new order conflicts with existing position.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{ALPACA_BASE_URL}/orders/resolve-conflicts",
                json={
                    "symbol": symbol,
                    "intended_side": side.lower(),
                    "intended_qty": qty,
                    "auto_resolve": True,
                },
            )

            # Extract key info you want
            result = resp.json()
            result_conflict_detected = result.get("conflicts_detected", {})
            # [DEBUG]: Print raw conflict resolution result
            print("[🛡️ RISK LAYER RESULT]", result)
            print()

            if result.get("status") == "no_conflict":
                print(f"   [🛡️ Risk Layer] No conflicts detected for {symbol}.")
                return {"has_conflict": False}
            
            # 1. CONFLICT STATUS
            has_conflict = result_conflict_detected["has_conflict"]
            print(f"🎯 CONFLICT: {has_conflict}")

            # 2. CURRENT POSITION (before resolution)
            if result_conflict_detected.get("current_position", None) is not None:
                current_pos = result_conflict_detected["current_position"]
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
                print(f"   [🛡️ Conflict Resolution] Action: {act}")
                if action_type == "closed_position":
                    current_position = result_conflict_detected.get("current_position", {})

                    vars_dict = db_trade_decision(
                        order_id=act["order_id"],
                        symbol=symbol,
                        action=action_type,
                        reasonings=f"[Trade Conflict] Closed {act['qty']:.1f} share(s) of {symbol}",
                        closed_position=closed_position(
                            qty=current_position.get("qty", 0),
                            side=current_position.get("side", ""),
                            market_value=current_position.get("market_value", 0),
                            avg_entry_price=current_position.get("avg_entry_price", 0),
                            pnl=current_position.get("unrealized_pl", 0),
                        ),
                        signal_id=signal_id
                    )
                elif action_type == "cancelled_orders":
                    vars_dict = db_trade_decision(
                        order_id="".join(act["order_ids"][:2]),
                        symbol=symbol,
                        action=action_type,
                        reasonings=f"[Trade Conflict] Cancelled {act['count']} pending order(s) for {symbol}",
                        signal_id=signal_id
                    )

                conflict_resolution.append(vars_dict)

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


def risk_evaluation_metrics(trade: TradingDecision, yahoo_data: YahooData, account_bp: str) -> RiskAssessment:
    account_bp = float(account_bp)

    current_price = yahoo_data.price
    atr = yahoo_data.atr14
    resistance = yahoo_data.resistance
    support = yahoo_data.support
    entry_price = trade.entry_price

    # 1. 🚨 DIRECTIONAL VALIDATION & AUTO-FIX
    issues = []
    adjusted_trade: TradingDecision = dataclasses.replace(trade)

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

    adjusted_trade.entry_price = entry_price

    if trade.action == TradeAction.BUY:
        # BUY: SL must be BELOW entry, TP must be ABOVE entry
        original_sl = trade.stop_loss
        original_tp = trade.take_profit

        new_sl = max(support, entry_price - atr)
        new_tp = min(resistance, entry_price + (atr * 2))

        adjusted_trade.stop_loss = new_sl
        adjusted_trade.take_profit = new_tp

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

    elif trade.action == TradeAction.SELL:
        # SELL: SL must be ABOVE entry, TP must be BELOW entry
        original_sl = trade.stop_loss
        original_tp = trade.take_profit

        new_tp = max(support, entry_price - (atr * 2))
        new_sl = min(resistance, entry_price + atr)

        adjusted_trade.take_profit = new_tp
        adjusted_trade.stop_loss = new_sl

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
        float(adjusted_trade.entry_price) - float(adjusted_trade.stop_loss)
    )
    reward_per_share = abs(
        float(adjusted_trade.take_profit) - float(adjusted_trade.entry_price)
    )
    actual_rr = reward_per_share / risk_per_share if risk_per_share > 0 else 0

    max_risk_pct = 0.05 if float(adjusted_trade.confidence) >= 0.8 else 0.03
    max_risk_dollars = account_bp * max_risk_pct
    suggested_qty = max_risk_dollars // current_price
    adjusted_trade.qty = suggested_qty  # Use suggested qty for 5% risk

    total_risk_dollars = suggested_qty * risk_per_share  # ✅ Now float * float
    risk_pct_account = (total_risk_dollars / account_bp) * 100
    
    # 3. 🎯 SCORING
    risk_score = float(adjusted_trade.confidence)
    near_resistance = abs(current_price - resistance) < atr
    risk_score += 0.2 if near_resistance else 0.0
    risk_score += 0.1 if atr > 5.0 else 0.0
    risk_score += 0.15 if actual_rr >= 1.5 else -0.1
    risk_score += 0.1 if risk_pct_account >= 2.0 else 0.0

    risk_metric = RiskMetrics(
        risk_score=round(min(risk_score, 1.5), 2),
        risk_per_share=f"${risk_per_share:.2f}",
        reward_per_share=f"${reward_per_share:.2f}",
        actual_rr=f"{actual_rr:.1f}:1",
        total_risk=f"${total_risk_dollars:.0f} ({risk_pct_account:.1f}%)",
        suggested_qty=f"{suggested_qty:.0f}",
        near_resistance=near_resistance,
        atr_distance=f"{atr:.1f}",
        max_risk_5pct=f"${max_risk_dollars:.0f}",
    )

    risk_assessment = RiskAssessment(
        risk_status="APPROVED" if risk_score >= 0.9 else "REVIEW",
        risk_score=round(min(risk_score, 1.5), 2),
        adjusted_trade=adjusted_trade,
        metrics=risk_metric,
        issues=issues,
    )

    return risk_assessment


## Printing helper
def print_risk_evaluation(evaluation_result: RiskAssessment):
    """Pretty print risk evaluation results"""
    # Header
    print("\n" + "=" * 60)
    print("🎯 RISK EVALUATION REPORT")
    print("=" * 60)

    # Status  
    status_emoji = "✅" if evaluation_result.risk_status == "APPROVED" else "⚠️"
    print(f"\n{status_emoji} STATUS: {evaluation_result.risk_status}")
    print(f"📊 RISK SCORE: {evaluation_result.risk_score:.2f}/1.50")

    # Trade Details
    trade = evaluation_result.adjusted_trade
    print("\n📋 TRADE SETUP")
    print(f"  Action:        {trade.action.value}")
    print(f"  Symbol:        {trade.ticker if hasattr(trade, 'ticker') else 'N/A'}")
    print(f"  Confidence:    {trade.confidence * 100:.0f}%")
    print(f"  Entry:         ${trade.entry_price:.2f}")
    print(f"  Stop Loss:     ${trade.stop_loss:.2f}")
    print(f"  Take Profit:   ${trade.take_profit:.2f}")
    print(f"  Quantity:      {trade.qty} shares")

    # Risk Metrics
    metrics = evaluation_result.metrics
    print("\n💰 RISK METRICS")
    print(f"  Risk/Share:    {metrics.risk_per_share}")
    print(f"  Reward/Share:  {metrics.reward_per_share}")
    print(f"  Actual R:R:    {metrics.actual_rr}")
    print(f"  Total Risk:    {metrics.total_risk}")

    # Position Sizing
    print("\n📐 POSITION SIZING")
    print(f"  Current Qty:   {trade.qty} shares")
    print(f"  Suggested Qty: {metrics.suggested_qty} shares (5% risk)")
    print(f"  Max Risk (5%): {metrics.max_risk_5pct}")

    # Technical Context
    print("\n📈 TECHNICAL CONTEXT")
    print(f"  Near Resistance: {'Yes ✅' if metrics.near_resistance else 'No'}")
    print(f"  ATR Distance:    {metrics.atr_distance}")

    # Thesis
    if hasattr(trade, 'thesis') and trade.thesis:
        print("\n💡 THESIS")
        # Wrap thesis text
        thesis = trade.thesis
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
    if evaluation_result.issues:
        print("\n⚠️ ADJUSTMENTS MADE")
        for issue in evaluation_result.issues:
            print(f"  • {issue}")
    else:
        print("\n✅ NO ADJUSTMENTS NEEDED")

    print("\n" + "=" * 60 + "\n")
