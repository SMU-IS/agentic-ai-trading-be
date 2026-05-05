from dataclasses import replace
from app.agents.state import AgentState, RiskAssessment, RiskMetrics, TradeAction, YahooTechnicalData, closed_position, db_trade_decision, TradingDecision, MarketData, RiskProfile, ProfileParams, RiskAdjResult
from typing import Dict, Any, List, Optional
import httpx
import asyncio
from app.core.config import env_config


ALPACA_BASE_URL = env_config.trading_service_url
BROKER_URL = env_config.trading_service_url
# Tunables risk profile
PROFILE_PARAMS: dict[RiskProfile, ProfileParams] = {
    RiskProfile.CONSERVATIVE: ProfileParams(
        penny_block       = True,
        min_confidence    = 0.70,
        max_entry_dev_pct = 0.01,   # kept for reference, entry no longer snapped
        min_rr            = 1.5,    # must achieve 1.5:1 — aligns with reasoning floor
        max_rr            = 3.0,    # cap at 3:1 — locks in realistic 2-5 day target
        min_vol_ratio     = 0.0,    # vol checks removed
        sl_atr_mult       = 1.0,    # reference only — SL preserved from reasoning
        tp_atr_mult       = 2.0,    # reference only — TP bounded by RR cap
        max_sl_pct        = 0.05,   # SL hard cap 5% from entry
        max_tp_pct        = 0.12,   # TP hard cap 12% from entry
        max_risk_pct      = 0.01,   # max 1% of buying power at risk per trade
        max_position_pct  = 0.03,   # max 3% of buying power per position
        low_vol_qty_mult  = 1.0,    # no vol penalty
        min_risk_score    = 0.72,   # block trade if score below this
    ),
    RiskProfile.AGGRESSIVE: ProfileParams(
        penny_block       = False,
        min_confidence    = 0.65,
        max_entry_dev_pct = 0.02,   # kept for reference, entry no longer snapped
        min_rr            = 1.5,    # reach for higher reward to justify larger risk
        max_rr            = 4.0,    # cap at 4:1 — allows more stretch, still realistic
        min_vol_ratio     = 0.0,    # vol checks removed
        sl_atr_mult       = 1.5,    # reference only — SL preserved from reasoning
        tp_atr_mult       = 2.5,    # reference only — TP bounded by RR cap
        max_sl_pct        = 0.10,   # SL hard cap 10% from entry
        max_tp_pct        = 0.20,   # TP hard cap 20% from entry
        max_risk_pct      = 0.03,   # max 3% of buying power at risk per trade
        max_position_pct  = 0.06,   # max 6% of buying power per position
        low_vol_qty_mult  = 1.0,    # no vol penalty
        min_risk_score    = 0.62,   # lower bar — accepts more trades with higher risk
    ),
}

async def evaluate_risk_for_user(
    user_id:       str,
    profile:       RiskProfile,
    order_details: TradingDecision,
    yahoo_data:    YahooTechnicalData,
    signal_id:     str,
) -> RiskAdjResult:
    """
    Evaluates risk for a single user + profile combination.
    Fetches buying power and conflict status, returns a RiskAdjResult.
    """
    account_bp, conflict = await asyncio.gather(
        fetch_buying_power(user_id),
        resolve_conflicting_position(
            order_details.ticker,
            order_details.action.value,
            10,
            user_id,
            signal_id
        ),
    )

    print(f"   [💰 Buying Power] user={user_id} | {account_bp}")

    assessment: RiskAssessment = await asyncio.to_thread(
        risk_evaluation_metrics,
        order_details, yahoo_data, account_bp, profile,
    )

    has_conflict     = conflict.get("has_conflict", False)
    current_position = conflict.get("current_position")
    trade_blocked    = assessment.risk_status == "BLOCKED" or assessment.adjusted_trade.qty == 0
    should_execute   = not (has_conflict and current_position is not None) and not trade_blocked

    print(f"   [🛡️ Risk] user={user_id} | profile={profile.value} | status={assessment.risk_status} | should_execute={should_execute}")
    return RiskAdjResult(
        user_id                = user_id,       
        profile                = profile,            
        adjusted_order_details = assessment.adjusted_trade,
        risk_evaluation        = assessment,
        should_execute         = should_execute,
        conflict_resolution    = conflict.get("conflict_resolution", {}),
    )


async def node_risk_adjust_trade(state: AgentState) -> AgentState:
    """
    Fetches all users per profile, evaluates risk concurrently,
    and stores results keyed by profile in state.
    """
    # If reasoning returned HOLD, skip evaluation — merge_orders handles the rest
    if not state.get("has_trade_opportunity", False):
        print("   [🛡️ Risk Layer] Skipping — reasoning returned HOLD")
        return {"standard_order_list": [], "all_conflict_resolutions": []}

    order_details: TradingDecision = state.get("order_details")
    signal_id:     str             = state.get("signal_id", "")
    market_data:   MarketData      = state.get("market_data")
    yahoo_data                     = market_data.yahoo if market_data else {}

    print("   [🛡️ Risk Layer] Fetching accounts per profile...")

    aggressive_accounts, conservative_accounts = await asyncio.gather(
        fetch_accounts_by_profile(RiskProfile.AGGRESSIVE),
        fetch_accounts_by_profile(RiskProfile.CONSERVATIVE),
    )

    print(f"   [🛡️ Risk Layer] aggressive={len(aggressive_accounts)} | conservative={len(conservative_accounts)} accounts")

    # ── Evaluate all users across both profiles concurrently ──────
    aggressive_tasks = [
        evaluate_risk_for_user(
            acc["id"], RiskProfile.AGGRESSIVE, order_details, yahoo_data, signal_id
        )
        for acc in aggressive_accounts
    ]
    conservative_tasks = [
        evaluate_risk_for_user(
            acc["id"], RiskProfile.CONSERVATIVE, order_details, yahoo_data, signal_id
        )
        for acc in conservative_accounts
    ]

    aggressive_results, conservative_results = await asyncio.gather(
        asyncio.gather(*aggressive_tasks),
        asyncio.gather(*conservative_tasks),
    )

    # ── Execution gate — any profile blocks if all users blocked ──
    should_execute = any(r["should_execute"] for r in [*aggressive_results, *conservative_results])
    order_list: list[RiskAdjResult] = [
        *aggressive_results,
        *conservative_results,
    ]

    print(f"   [🛡️ Risk Layer] should_execute={should_execute}")

    return {
        "standard_order_list":      order_list,
        "all_conflict_resolutions": [x["conflict_resolution"] for x in order_list],
    }

async def fetch_accounts_by_profile(profile: RiskProfile) -> List[dict]:
    """
    Fetch accounts filtered by risk profile from trading decisions service.
    Returns: [{"id": "user_id"}, ...]
    """
    profile_slug = profile.value.lower()  # "aggressive" | "conservative"
    url = f"{BROKER_URL}/decisions/trading-accounts/{profile_slug}"

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()

            accounts = resp.json()
            return [{"id": account["user_id"]} for account in accounts]

        except httpx.HTTPStatusError as e:
            print(f"   [❌ Accounts] Failed to fetch {profile_slug} accounts: {e.response.status_code}")
            return []
        except httpx.TimeoutException:
            print(f"   [❌ Accounts] Timeout fetching {profile_slug} accounts")
            return []
        except Exception as e:
            print(f"   [❌ Accounts] Unexpected error: {e}")
            return []

async def fetch_buying_power(user_id) -> float:
    """Fetch Yahoo historical + key indicators for LLM prompts."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{ALPACA_BASE_URL}/account", headers={"x-user-id": user_id})
            if resp.status_code != 200:
                return {"error": "Error fetching buying power"}

            data = resp.json()

            if "non_marginable_buying_power" in data:
                return float(data.get("non_marginable_buying_power", 0))

            return {"error": "No valid buying power"}

        except Exception as e:
            return {"error": str(e)}


async def resolve_conflicting_position(
    symbol: str,
    side: str,
    qty: float,
    user_id: str,
    signal_id: str = "",
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
                    "auto_resolve": False, # just check for conflicts, don't auto-resolve here
                },
                headers={"x-user-id": user_id}
            )

            # Extract key info you want
            result = resp.json()
            print("conflict resolutions prints")
            print("==============================")
            print(result)
            print()
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

## Risk Eval / Trade Adjustment Layer

def _atr_guard(atr: float, price: float) -> float:
    """
    ATR sanity check: if ATR < 0.5% of price it's almost certainly
    intraday tick ATR, not a daily figure. Floor it at 1% of price
    so SL/TP buffers are never sub-penny nonsense.
    """
    floor = price * 0.01
    if atr < floor:
        return floor
    return atr


def risk_evaluation_metrics(
    trade:      TradingDecision,
    yahoo_data: YahooTechnicalData,
    account_bp: str,
    profile:    RiskProfile = RiskProfile.CONSERVATIVE,
) -> RiskAssessment:

    account_bp   = float(account_bp)
    p            = PROFILE_PARAMS[profile]
    issues       = []
    blocks       = []
    adjusted     = replace(trade)

    current_price = yahoo_data.current_price
    atr           = _atr_guard(yahoo_data.atr14, current_price)
    support       = yahoo_data.support
    resistance    = yahoo_data.resistance
    is_sell       = trade.action == TradeAction.SELL

    # ── GATE 1: PENNY STOCK ──────────────────────────────────────
    if yahoo_data.is_penny and p.penny_block:
        blocks.append(
            f"[{profile.value.upper()}] Penny stock blocked — price "
            f"${current_price:.2f} qualifies as penny stock."
        )
        return _blocked_assessment(adjusted, blocks)

    # ── GATE 2: CONFIDENCE ───────────────────────────────────────
    if trade.confidence < p.min_confidence:
        blocks.append(
            f"[{profile.value.upper()}] Confidence {trade.confidence:.0%} "
            f"below minimum {p.min_confidence:.0%}."
        )
        return _blocked_assessment(adjusted, blocks)

    # ── ENTRY: PRESERVED FROM REASONING ─────────────────────────
    # Reasoning sets entry at structural levels (anticipatory or at-market).
    # Risk layer does not snap or override entry — it is trusted as-is.
    market_ref = yahoo_data.current_price
    dev_pct    = abs(trade.entry_price - market_ref) / market_ref
    if dev_pct > p.max_entry_dev_pct:
        issues.append({
            "field":      "entry_price",
            "reason":     f"Entry deviates {dev_pct:.1%} from market (anticipatory or stale).",
            "adjustment": f"Entry ${trade.entry_price:.2f} preserved — reasoning owns this level.",
        })

    entry = adjusted.entry_price   # unchanged

    # ── STOP LOSS: PRESERVED FROM REASONING ──────────────────────
    # SL is set by reasoning at the structural invalidation level with buffer.
    # Risk layer enforces a hard % cap only — does not move SL inward.
    sl_cap_pct = entry * (1 + p.max_sl_pct) if is_sell else entry * (1 - p.max_sl_pct)
    if is_sell and trade.stop_loss > sl_cap_pct:
        adjusted.stop_loss = sl_cap_pct
        issues.append({
            "field":      "stop_loss",
            "reason":     f"SL ${trade.stop_loss:.2f} exceeds hard cap {p.max_sl_pct:.0%} from entry.",
            "adjustment": f"${trade.stop_loss:.2f} → ${sl_cap_pct:.2f}",
        })
    elif not is_sell and trade.stop_loss < sl_cap_pct:
        adjusted.stop_loss = sl_cap_pct
        issues.append({
            "field":      "stop_loss",
            "reason":     f"SL ${trade.stop_loss:.2f} exceeds hard cap {p.max_sl_pct:.0%} from entry.",
            "adjustment": f"${trade.stop_loss:.2f} → ${sl_cap_pct:.2f}",
        })

    # ── TAKE PROFIT: TRUST REASONING, BLOCK ON VIOLATIONS ───────
    # Reasoning TP is set at structural levels (support/resistance/SMA).
    # Preserve it as-is. Only override if it breaches hard safety rules.
    risk_per_share   = abs(entry - adjusted.stop_loss)
    reasoning_reward = abs(trade.take_profit - entry)
    reasoning_rr     = reasoning_reward / risk_per_share if risk_per_share > 0 else 0.0

    adjusted.take_profit = trade.take_profit  # preserve reasoning TP

    # BLOCK: RR below profile minimum — don't stretch TP, reject the trade
    if reasoning_rr < p.min_rr:
        blocks.append(
            f"[{profile.value.upper()}] R:R {reasoning_rr:.2f}:1 below profile minimum {p.min_rr}:1. "
            f"Reasoning TP ${trade.take_profit:.2f} preserved — trade blocked rather than stretching TP."
        )
        return _blocked_assessment(adjusted, blocks)

    # CAP: TP beyond hard % limit — pull back to cap
    tp_cap_pct = entry * (1 - p.max_tp_pct) if is_sell else entry * (1 + p.max_tp_pct)
    if is_sell and adjusted.take_profit < tp_cap_pct:
        adjusted.take_profit = round(tp_cap_pct, 4)
        issues.append({
            "field":      "take_profit",
            "reason":     f"TP exceeds hard cap {p.max_tp_pct:.0%} from entry.",
            "adjustment": f"Capped at ${tp_cap_pct:.2f}",
        })
    elif not is_sell and adjusted.take_profit > tp_cap_pct:
        adjusted.take_profit = round(tp_cap_pct, 4)
        issues.append({
            "field":      "take_profit",
            "reason":     f"TP exceeds hard cap {p.max_tp_pct:.0%} from entry.",
            "adjustment": f"Capped at ${tp_cap_pct:.2f}",
        })

    issues.append({
        "field":      "sl_tp_method",
        "reason":     "SL and TP both preserved from reasoning (structural levels).",
        "adjustment": f"Reasoning TP ${trade.take_profit:.2f} (RR {reasoning_rr:.1f}:1) accepted.",
    })

    # ── RISK CALCULATIONS ────────────────────────────────────────
    risk_per_share   = abs(entry - adjusted.stop_loss)
    reward_per_share = abs(adjusted.take_profit - entry)
    actual_rr        = reward_per_share / risk_per_share if risk_per_share > 0 else 0.0

    # ── POSITION SIZING ──────────────────────────────────────────
    max_risk_dollars    = account_bp * p.max_risk_pct
    max_position_dollars = account_bp * p.max_position_pct

    # Size by risk first, then cap by max position
    qty_by_risk     = max_risk_dollars / risk_per_share if risk_per_share > 0 else 0
    qty_by_position = max_position_dollars / entry      if entry > 0          else 0
    qty             = min(qty_by_risk, qty_by_position)

    qty = max(1.0, round(qty))
    adjusted.qty = qty

    total_risk_dollars = qty * risk_per_share
    risk_pct_account   = (total_risk_dollars / account_bp) * 100

    # ── SCORING ──────────────────────────────────────────────────
    # Normalised 0–1. Start from confidence, apply bounded bonuses.
    score = trade.confidence

    # Reward good R:R
    if actual_rr >= 3.0:
        score += 0.10
    elif actual_rr >= 2.0:
        score += 0.05
    elif actual_rr < p.min_rr:
        score -= 0.10

    # Bearish confirmation for SELL (and vice-versa)
    if is_sell and yahoo_data.macd_bearish:
        score += 0.05
    elif not is_sell and yahoo_data.macd_bullish:
        score += 0.05

    # Directional RSI alignment
    if is_sell and yahoo_data.rsi > 60:
        score += 0.05   # overbought → SELL confirmed
    elif not is_sell and yahoo_data.rsi < 40:
        score += 0.05   # oversold → BUY confirmed

    # Near key level = higher risk
    near_resistance = abs(current_price - resistance) < atr
    near_support    = abs(current_price - support)    < atr
    if (is_sell and near_resistance) or (not is_sell and near_support):
        score += 0.05   # price at the right structural level

    score = round(min(max(score, 0.0), 1.0), 3)   # hard clamp [0, 1]

    # ── ASSEMBLE ─────────────────────────────────────────────────
    risk_metric = RiskMetrics(
        risk_score      = score,
        risk_per_share  = f"${risk_per_share:.2f}",
        reward_per_share= f"${reward_per_share:.2f}",
        actual_rr       = f"{actual_rr:.1f}:1",
        total_risk      = f"${total_risk_dollars:.0f} ({risk_pct_account:.1f}%)",
        suggested_qty   = f"{qty:.0f}",
        near_resistance = near_resistance,
        atr_distance    = f"{atr:.4f}",
        max_risk_5pct   = f"${max_risk_dollars:.0f}",
    )

    # APPROVED only if score meets profile threshold — REVIEW is treated as BLOCKED
    status = "APPROVED" if score >= p.min_risk_score and not blocks else "BLOCKED"

    return RiskAssessment(
        risk_status   = status,
        risk_score    = score,
        adjusted_trade= adjusted,
        metrics       = risk_metric,
        issues        = issues,
    )


def _blocked_assessment(
    trade:  TradingDecision,
    blocks: list[str],
    issues: Optional[list] = None,
) -> RiskAssessment:
    """Return a zero-qty BLOCKED assessment without touching the trade."""
    blocked_trade      = replace(trade)
    blocked_trade.qty  = 0.0
    return RiskAssessment(
        risk_status   = "BLOCKED",
        risk_score    = 0.0,
        adjusted_trade= blocked_trade,
        metrics       = RiskMetrics(
            risk_score      = 0.0,
            risk_per_share  = "$0.00",
            reward_per_share= "$0.00",
            actual_rr       = "0.0:1",
            total_risk      = "$0 (0.0%)",
            suggested_qty   = "0",
            near_resistance = False,
            atr_distance    = "0.0",
            max_risk_5pct   = "$0",
        ),
        issues        = (issues or []) + [{"field": "blocked", "reason": b, "adjustment": "Trade rejected."} for b in blocks],
    )


