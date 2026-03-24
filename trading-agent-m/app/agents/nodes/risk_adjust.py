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
        min_confidence    = 0.80,
        max_entry_dev_pct = 0.01,
        min_rr            = 2.0,
        min_vol_ratio     = 0.8,
        sl_atr_mult       = 1.0,
        tp_atr_mult       = 2.0,
        max_risk_pct      = 0.005,
        max_position_pct  = 0.02,
        low_vol_qty_mult  = 0.5,
    ),
    RiskProfile.AGGRESSIVE: ProfileParams(
        penny_block       = False,
        min_confidence    = 0.70,
        max_entry_dev_pct = 0.02,
        min_rr            = 1.5,
        min_vol_ratio     = 0.0,
        sl_atr_mult       = 1.5,
        tp_atr_mult       = 3.0,
        max_risk_pct      = 0.015,
        max_position_pct  = 0.05,
        low_vol_qty_mult  = 1.0,
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
    should_execute   = not (has_conflict and current_position is not None)

    print(f"   [🛡️ Risk] user={user_id} | profile={profile.value} | should_execute={should_execute}")

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
    # print()
    # print(aggressive_results)
    # print()
    # print(conservative_results)

    # print()
    # ── Execution gate — any profile blocks if all users blocked ──
    should_execute = any(r["should_execute"] for r in [*aggressive_results, *conservative_results])
    order_list: list[RiskAdjResult] = [
        *aggressive_results,
        *conservative_results,
    ]

    print(f"   [🛡️ Risk Layer] should_execute={should_execute}")

    state["should_execute"] = should_execute
    state["order_list"] = order_list
    return state

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
            resp = await client.get(f"{ALPACA_BASE_URL}/account", headers={"x_user_id": user_id})
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
                    "auto_resolve": True,
                },
                headers={"x_user_id": user_id}
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

    # ── ADJUSTMENT 1: ENTRY PRICE ────────────────────────────────
    # Snap to bid (SELL) or ask (BUY) when entry deviates too far.
    market_ref    = yahoo_data.current_price   # replace with bid/ask if available
    dev_pct       = abs(trade.entry_price - market_ref) / market_ref

    if dev_pct > p.max_entry_dev_pct:
        original_entry = trade.entry_price
        adjusted.entry_price = market_ref
        issues.append({
            "field":      "entry_price",
            "reason":     f"Entry deviates {dev_pct:.1%} > {p.max_entry_dev_pct:.0%} max.",
            "adjustment": f"${original_entry:.2f} → ${market_ref:.2f} (current market)",
        })

    entry = adjusted.entry_price

    # ── ADJUSTMENT 2: STOP LOSS, TAKE PROFIT ──────────────────────────────────
    correct_sl, correct_tp, level_method = _calculate_sl_tp(
        entry, trade.action, yahoo_data, profile
    )
    issues.append({
    "field":      "sl_tp_method",
    "reason":     "SL/TP anchored to structural levels, not ATR multiples.",
    "adjustment": level_method,
})
    adjusted.take_profit = correct_tp
    adjusted.stop_loss = correct_sl

    # ── RISK CALCULATIONS ────────────────────────────────────────
    risk_per_share   = abs(entry - adjusted.stop_loss)
    reward_per_share = abs(adjusted.take_profit - entry)
    actual_rr        = reward_per_share / risk_per_share if risk_per_share > 0 else 0.0

    # ── GATE 3: R:R ──────────────────────────────────────────────
    if actual_rr < p.min_rr:
        if profile == RiskProfile.CONSERVATIVE:
            blocks.append(
                f"[CONSERVATIVE] R:R {actual_rr:.2f} below minimum {p.min_rr}. "
                "Widen TP or tighten SL."
            )
            # return _blocked_assessment(adjusted, blocks, issues) # Block as risk reward ratio is below minimum of 2
        else:
            issues.append({
                "field":      "risk_reward",
                "reason":     f"R:R {actual_rr:.2f} below aggressive minimum {p.min_rr}.",
                "adjustment": "Proceeding — aggressive profile allows lower R:R.",
            })

    # ── POSITION SIZING ──────────────────────────────────────────
    max_risk_dollars    = account_bp * p.max_risk_pct
    max_position_dollars = account_bp * p.max_position_pct

    # Size by risk first, then cap by max position
    qty_by_risk     = max_risk_dollars / risk_per_share if risk_per_share > 0 else 0
    qty_by_position = max_position_dollars / entry      if entry > 0          else 0
    qty             = min(qty_by_risk, qty_by_position)

    # Volume liquidity penalty
    if yahoo_data.vol_ratio < p.min_vol_ratio and p.low_vol_qty_mult < 1.0:
        original_qty = qty
        qty *= p.low_vol_qty_mult
        issues.append({
            "field":      "quantity",
            "reason":     (
                f"Volume {yahoo_data.vol_ratio:.1f}× below "
                f"{p.min_vol_ratio:.1f}× threshold."
            ),
            "adjustment": (
                f"{original_qty:.0f} → {qty:.0f} "
                f"(×{p.low_vol_qty_mult} liquidity discount)"
            ),
        })

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

    # Penalise low volume
    if yahoo_data.vol_ratio < 0.5:
        score -= 0.05

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

    status = "APPROVED" if score >= 0.85 and not blocks else "REVIEW"

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


def _calculate_sl_tp(
    entry:      float,
    action:     TradeAction,
    yahoo:      YahooTechnicalData,
    profile:    RiskProfile,
) -> tuple[float, float, str]:
    """
    Returns (stop_loss, take_profit, method_used).
    Priority: structural levels > band edges > SMA > 3D range.
    ATR is used only as a minimum buffer guard, not as the primary source.
    """
    is_sell = action == TradeAction.SELL
    atr     = _atr_guard(yahoo.atr14, yahoo.current_price)

    # ── STOP LOSS ────────────────────────────────────────────────
    sl_candidates: list[tuple[float, str]] = []

    # 1. SMA50 — thesis invalidation level (strongest)
    if yahoo.sma50 and yahoo.sma50 > 0:
        if is_sell and yahoo.sma50 > entry:
            sl_candidates.append((yahoo.sma50 * 1.002, "SMA50 + 0.2% buffer"))
        elif not is_sell and yahoo.sma50 < entry:
            sl_candidates.append((yahoo.sma50 * 0.998, "SMA50 - 0.2% buffer"))

    # 2. Bollinger Band edge — expansion/squeeze invalidation
    if is_sell and yahoo.bb_upper > entry:
        sl_candidates.append((yahoo.bb_upper, "BB upper band"))
    elif not is_sell and yahoo.bb_lower < entry:
        sl_candidates.append((yahoo.bb_lower, "BB lower band"))

    # 3. 3D range boundary — momentum invalidation
    if is_sell:
        sl_candidates.append((yahoo.high_3d, "3D range high"))
    else:
        sl_candidates.append((yahoo.low_3d, "3D range low"))

    # Pick the SL closest to entry that still clears a minimum ATR buffer.
    # Conservative: tighter SL (closest valid candidate).
    # Aggressive: allow the furthest for more breathing room.
    min_sl_distance = atr * 0.5   # hard floor — SL can never be < 0.5 ATR away

    valid_sl = [
        (sl, method) for sl, method in sl_candidates
        if abs(sl - entry) >= min_sl_distance
        and (sl > entry if is_sell else sl < entry)
    ]

    if profile == RiskProfile.CONSERVATIVE:
        # Tightest valid SL = smallest loss if wrong
        valid_sl.sort(key=lambda x: abs(x[0] - entry))
    else:
        # Widest valid SL = more room before invalidation
        valid_sl.sort(key=lambda x: abs(x[0] - entry), reverse=True)

    if valid_sl:
        stop_loss, sl_method = valid_sl[0]
    else:
        # Fallback only if no structural level qualifies
        mult = 1.0 if profile == RiskProfile.CONSERVATIVE else 1.5
        stop_loss  = entry + atr * mult if is_sell else entry - atr * mult
        sl_method  = f"ATR fallback ({mult}×)"

    # ── TAKE PROFIT ──────────────────────────────────────────────
    tp_candidates: list[tuple[float, str]] = []

    # 1. Hard structural support/resistance (primary target)
    if is_sell and yahoo.support < entry:
        tp_candidates.append((yahoo.support, "structural support"))
    elif not is_sell and yahoo.resistance > entry:
        tp_candidates.append((yahoo.resistance, "structural resistance"))

    # 2. BB middle (mean-reversion target — ideal for post-spike fades)
    if yahoo.bb_middle and yahoo.bb_middle > 0:
        if is_sell and yahoo.bb_middle < entry:
            tp_candidates.append((yahoo.bb_middle, "BB midline / SMA20"))
        elif not is_sell and yahoo.bb_middle > entry:
            tp_candidates.append((yahoo.bb_middle, "BB midline / SMA20"))

    # 3. 3D range boundary (near-term acceptance zone)
    if is_sell and yahoo.low_3d < entry:
        tp_candidates.append((yahoo.low_3d, "3D range low"))
    elif not is_sell and yahoo.high_3d > entry:
        tp_candidates.append((yahoo.high_3d, "3D range high"))

    # Conservative: take profit early (closest target).
    # Aggressive: reach for the furthest structural level.
    if tp_candidates:
        if profile == RiskProfile.CONSERVATIVE:
            tp_candidates.sort(key=lambda x: abs(x[0] - entry))
        else:
            tp_candidates.sort(key=lambda x: abs(x[0] - entry), reverse=True)
        take_profit, tp_method = tp_candidates[0]
    else:
        mult = 2.0 if profile == RiskProfile.CONSERVATIVE else 3.0
        take_profit = entry - atr * mult if is_sell else entry + atr * mult
        tp_method   = f"ATR fallback ({mult}×)"

    method = f"SL: {sl_method} | TP: {tp_method}"
    return round(stop_loss, 4), round(take_profit, 4), method