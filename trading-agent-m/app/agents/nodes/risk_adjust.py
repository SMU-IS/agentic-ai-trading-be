from dataclasses import replace
from app.agents.state import AgentState, RiskAssessment, RiskMetrics, TradeAction, YahooTechnicalData, TradingDecision, RiskProfile, ProfileParams, RiskAdjResult
from typing import Dict, Any, List, Optional
import httpx
import asyncio
from app.core.config import env_config


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

def build_profile_params(risk_settings: dict, profile: RiskProfile) -> ProfileParams:
    """
    Overlay user's risk_settings onto the hardcoded preset.
    Non-configurable fields (atr multipliers, vol ratios) are inherited from the preset.
    """
    preset = PROFILE_PARAMS.get(profile, PROFILE_PARAMS[RiskProfile.AGGRESSIVE])
    return replace(
        preset,
        penny_block      = risk_settings.get("penny_block",      preset.penny_block),
        min_confidence   = float(risk_settings.get("min_confidence",   preset.min_confidence)),
        min_rr           = float(risk_settings.get("min_rr",           preset.min_rr)),
        max_sl_pct       = float(risk_settings.get("max_sl_pct",       preset.max_sl_pct)),
        max_tp_pct       = float(risk_settings.get("max_tp_pct",       preset.max_tp_pct)),
        max_risk_pct     = float(risk_settings.get("max_risk_pct",     preset.max_risk_pct)),
        max_position_pct = float(risk_settings.get("max_position_pct", preset.max_position_pct)),
        min_risk_score   = float(risk_settings.get("min_risk_score",   preset.min_risk_score)),
    )


async def evaluate_risk_for_user(
    user_id:       str,
    profile:       RiskProfile,
    order_details: TradingDecision,
    yahoo_data:    YahooTechnicalData,
    risk_settings: Optional[dict] = None,
) -> RiskAdjResult:
    """
    Evaluates risk for a single user + profile combination.
    Fetches buying power and conflict status, returns a RiskAdjResult.
    risk_settings: user's agent-settings risk_settings dict (pre-fetched by reasoning node).
    """
    account_bp, conflict = await asyncio.gather(
        fetch_buying_power(user_id),
        resolve_conflicting_position(
            order_details.ticker,
            order_details.action.value,
            10,
            user_id,
        ),
    )

    print(f"   [💰 Buying Power] user={user_id} | {account_bp}")

    profile_params = build_profile_params(risk_settings or {}, profile)

    assessment: RiskAssessment = await asyncio.to_thread(
        risk_evaluation_metrics,
        order_details, yahoo_data, account_bp, profile, profile_params,
    )

    has_conflict  = conflict.get("has_conflict", False)
    trade_blocked = assessment.risk_status == "BLOCKED" or assessment.adjusted_trade.qty == 0
    should_execute = not has_conflict and not trade_blocked

    print(f"   [🛡️ Risk] user={user_id} | profile={profile.value} | status={assessment.risk_status} | should_execute={should_execute}")
    return RiskAdjResult(
        user_id                = user_id,       
        profile                = profile,            
        adjusted_order_details = assessment.adjusted_trade,
        risk_evaluation        = assessment,
        should_execute         = should_execute,
        conflict_resolution    = conflict.get("conflict_resolution", {}),
    )


async def node_risk_adjust_v2(state: AgentState) -> dict:
    """
    V2 risk adjust node — consumes profile_decisions from node_profile_reasoning_v2.
    Evaluates risk per user using their own risk_settings, outputs order_list.
    """
    profile_decisions: list[dict] = state.get("profile_decisions") or []
    if not profile_decisions:
        print("   [🛡️ Risk V2] No profile decisions — skipping")
        return {"order_list": [], "should_execute": False}

    market_data = state.get("market_data")
    yahoo_data  = market_data.yahoo if market_data else None

    tasks = []
    for pd in profile_decisions:
        profile            = pd["profile"]
        decision           = pd["decision"]
        user_ids           = pd["user_ids"]
        user_risk_settings = pd.get("user_risk_settings", {})

        for user_id in user_ids:
            tasks.append(
                evaluate_risk_for_user(
                    user_id       = user_id,
                    profile       = profile,
                    order_details = decision,
                    yahoo_data    = yahoo_data,
                    risk_settings = user_risk_settings.get(user_id, {}),
                )
            )

    print(f"   [🛡️ Risk V2] {len(tasks)} user evaluation(s) in flight...")
    results: list[RiskAdjResult] = list(await asyncio.gather(*tasks))

    should_execute = any(r.get("should_execute", False) for r in results)
    executable     = sum(1 for r in results if r.get("should_execute"))
    print(f"   [🛡️ Risk V2] should_execute={should_execute} | {executable}/{len(results)} executable")

    return {
        "order_list":     results,
        "should_execute": should_execute,
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
            resp = await client.get(f"{BROKER_URL}/account", headers={"x-user-id": user_id})
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
) -> Dict[str, Any]:
    """
    Check whether a new order conflicts with existing positions or pending orders.
    Returns {"has_conflict": bool, "conflict_resolution": []}.
    Any conflict blocks execution — caller sets should_execute=False.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{BROKER_URL}/orders/resolve-conflicts",
                json={
                    "symbol":        symbol,
                    "intended_side": side.lower(),
                    "intended_qty":  qty,
                    "auto_resolve":  False,
                },
                headers={"x-user-id": user_id},
            )
            result    = resp.json()
            conflicts = result.get("conflicts", {})
            has_conflict = conflicts.get("has_conflict", False)

            if has_conflict:
                orders = conflicts.get("conflicting_orders", [])
                print(f"   [⚠️  Conflict] {symbol} user={user_id} | {len(orders)} conflicting order(s)")
            else:
                print(f"   [✅ No Conflict] {symbol} user={user_id}")

            return {"has_conflict": has_conflict, "conflict_resolution": []}

        except Exception as e:
            print(f"   [❌ Conflict Check] {symbol} user={user_id} | {e}")
            return {"has_conflict": False, "conflict_resolution": []}

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
    trade:          TradingDecision,
    yahoo_data:     YahooTechnicalData,
    account_bp:     str,
    profile:        RiskProfile = RiskProfile.CONSERVATIVE,
    profile_params: Optional[ProfileParams] = None,
) -> RiskAssessment:

    account_bp   = float(account_bp)
    p            = profile_params if profile_params is not None else PROFILE_PARAMS[profile]
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


