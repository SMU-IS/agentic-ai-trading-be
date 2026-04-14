import asyncio
import json
import re
from langchain_core.prompts import ChatPromptTemplate

from app.agents.state import (
    AgentState, MarketData, RiskProfile, SignalData,
    TradingDecision, TradeAction, RiskAdjResult,
    RiskAssessment, RiskMetrics,
)
from app.agents.nodes.risk_adjust import fetch_accounts_by_profile, fetch_buying_power


# ── Per-profile system prompts ────────────────────────────────────────────────
# Add new profiles here. Each gets its own LLM call with a tailored system message.

PROFILE_SYSTEM_PROMPTS: dict[RiskProfile, str] = {
    RiskProfile.CUSTOM: """You are a conservative short-term swing trader (2-5 day horizon).
Your priority is capital preservation. You trade high-conviction setups only.

ENTRY RULES:
- STRONG catalyst: proceed if at least 1 confirming factor (candle OR RSI OR key level).
- WEAK catalyst: require ALL THREE of (RSI extreme + price at structural level + confirming candle). If any missing, return HOLD.
- When in doubt, return HOLD. Missed trades cost nothing. Bad trades cost capital.

POSITION RULES:
- Max qty: 5 shares.
- Entry: at-market only. Anticipatory entries only when RSI <15 or >90.
- SL buffer: 0.15x ATR beyond structural level (tighter than standard).
- Minimum RR: 1.5:1. If not achievable with tight SL, return HOLD.

HOLD BIAS: Err toward HOLD on mixed signals. Only take setups where the thesis is clean and unambiguous.

Return ONLY valid JSON. No explanations outside the JSON block.""",
}

# Shared human prompt template (same market data, profile-specific system above)
_HUMAN_TEMPLATE = """MARKET DATA FOR {ticker}:
All fields below are present. Do not state that any field is unavailable or missing.

Field reference:
- Current Price: live broker quote (use this as current_stock_price)
- Candle: yesterday's OHLCV candle type, body%, body-to-range ratio
- Range: yesterday's Low - High, ATR14 (14-day average true range in dollars)
- RSI: momentum oscillator 0-100. OVERBOUGHT label = above 75. OVERSOLD label = below 30.
- SMA20 / SMA50 / SMA200: simple moving averages
- MACD / Signal / Histogram: histogram positive = bullish, negative = bearish
- BB Lower / Upper / Position%: Bollinger Bands. 0% = lower band, 100% = upper band
- Support / Resistance: structural levels from 30-day price history
- 3D Range: highest high and lowest low over last 3 days
- Bid / Ask / Spread: live broker quote

{market_summary}

---

Ticker: {ticker}
News Summary: {romour_summary}
Catalyst Credibility: {credibility} ({credibility_reason})
Initial Signal Direction: {trade_signal}
Signal Confidence: {confidence}
Signal Rationale: {trade_rationale}

ACCOUNT:
Available Buying Power: ${buying_power}

NOTE: Derive your own entry, SL, and TP from current price and ATR. Do not inherit the signal's levels.

ENTRY PRICING STEPS: Follow user trading strategy instructions.

UNIVERSAL RULES:
For SELL: stop_loss above entry, take_profit below entry.
For BUY: stop_loss below entry, take_profit above entry.
Do not add comments to JSON. No special characters in thesis.

Return in this exact JSON format:
{{
"action": "BUY" | "SELL" | "HOLD",
"confidence": 0.0-1.0,
"entry_price": float,
"stop_loss": float,
"take_profit": float,
"qty": float,
"risk_reward": "X:1",
"thesis": "...",
"current_stock_price": float
}}

If no valid trade, return action as HOLD with qty 0."""


def _build_market_summary(state: AgentState) -> str:
    if not state.get("market_data"):
        return "No market data available."
    md: MarketData = state["market_data"]
    y = md.yahoo
    a = md.alpaca

    def _f(v, fmt=""):
        if v is None: return "N/A"
        try: return f"{v:{fmt}}"
        except: return str(v)

    rsi_label = "OVERSOLD" if y.rsi and y.rsi < 30 else "OVERBOUGHT" if y.rsi and y.rsi > 75 else "NEUTRAL"
    spread_pct = (a.spread / a.latest_trade.price * 100) if a.latest_trade.price else 0.0

    return f"""PRICE ACTION SUMMARY:
- Current Price: ${_f(a.latest_trade.price, '.3f')} (live broker quote)
- Candle: {y.candle_type.upper()} (body {_f(y.body_size, '.1f')}%, {_f(y.body_pct, '.0%')} of range)
- Range: ${_f(y.low, '.3f')} - ${_f(y.high, '.3f')} | ATR14: ${_f(y.atr14, '.3f')}
- 3D Range: ${_f(y.low_3d, '.3f')} - ${_f(y.high_3d, '.3f')}
- Penny Stock: {'YES' if y.is_penny else 'NO'}

TECHNICAL INDICATORS:
- RSI: {_f(y.rsi, '.1f')} ({rsi_label})
- SMA20: ${_f(y.sma20, '.3f')} | SMA50: ${_f(y.sma50, '.3f')} | SMA200: ${_f(y.sma200, '.3f')}
- MACD: {_f(y.macd, '.4f')} | Signal: {_f(y.macd_signal, '.4f')} | Histogram: {_f(y.macd_histogram, '+.4f')}
- BB Lower: ${_f(y.bb_lower, '.3f')} | BB Upper: ${_f(y.bb_upper, '.3f')} | BB Middle: ${_f(y.bb_middle, '.3f')} | Position: {_f(y.bb_position, '.0%')}

MARKET STRUCTURE:
- Support: ${_f(y.support, '.3f')} | Resistance: ${_f(y.resistance, '.3f')}
- Data Period: {y.period_summary}

LIVE BROKER QUOTE ({a.latest_trade.symbol}, {a.latest_trade.timestamp}):
- Bid: ${_f(a.latest_quote.bid_price, '.2f')} x {a.latest_quote.bid_size} | Ask: ${_f(a.latest_quote.ask_price, '.2f')} x {a.latest_quote.ask_size}
- Spread: ${_f(a.spread, '.3f')} ({spread_pct:.2f}%)"""


def _parse_profile_json(content: str, profile: RiskProfile, ticker: str) -> TradingDecision:
    content = content.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL | re.IGNORECASE)
    raw = match.group(1) if match else re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", content)
    raw = raw if isinstance(raw, str) else (raw.group(0) if raw else content)
    raw = re.sub(r"//.*?(?=\n|$)", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"/\*.*?\*/", "", raw, flags=re.DOTALL)
    raw = raw.replace("True", "true").replace("False", "false")
    data = json.loads(raw)
    decision = TradingDecision.from_dict(data)
    decision.ticker = ticker
    return decision


async def _fetch_agent_settings(user_id: str) -> dict:
    """Fetch agent settings (including custom_prompt) for a user from trading-service."""
    import httpx
    from app.core.config import env_config
    url = f"{env_config.trading_service_url}/decisions/agent-settings/{user_id}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return resp.json()
    except Exception as e:
        print(f"   [⚠️ Profile:custom] Failed to fetch settings for {user_id}: {e}")
    return {}


def _hold_decision(ticker: str) -> TradingDecision:
    return TradingDecision(
        action=TradeAction.HOLD, confidence=0.0, entry_price=0.0,
        stop_loss=0.0, take_profit=0.0, qty=0.0,
        risk_reward="0:1", thesis="Profile reasoning error - defaulting to HOLD",
        current_stock_price=0.0, ticker=ticker,
    )


async def _run_profile_llm(
    llm,
    profile: RiskProfile,
    input_vars: dict,
    ticker: str,
    max_retries: int = 2,
    system_prompt: str = None,
) -> TradingDecision:
    system_prompt = system_prompt or PROFILE_SYSTEM_PROMPTS[profile]
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", _HUMAN_TEMPLATE),
    ])
    chain = prompt | llm

    content = ""
    for attempt in range(max_retries + 1):
        try:
            response = await chain.ainvoke(input_vars)
            content = (response.content or "").strip()
            if not content:
                finish = getattr(response, "response_metadata", {}).get("finish_reason", "unknown")
                raise ValueError(f"LLM returned empty content (finish_reason={finish})")
            decision = _parse_profile_json(content, profile, ticker)
            print(f"   [🎯 Profile:{profile.value}] Parsed on attempt {attempt + 1} — action={decision.action}")
            return decision
        except Exception as e:
            print(f"   [⚠️ Profile:{profile.value}] Attempt {attempt + 1} failed: {e}")
            if content:
                print(f"   [⚠️ Profile:{profile.value}] Raw content: {content[:300]}")
            if attempt < max_retries:
                await asyncio.sleep(1.5 * (attempt + 1))

    print(f"   [❌ Profile:{profile.value}] All retries failed — defaulting to HOLD")
    return _hold_decision(ticker)


async def node_profile_reasoning(llm, state: AgentState) -> AgentState:
    """
    Parallel reasoning node. Runs a profile-specific LLM prompt for each
    risk profile, then applies per-user risk evaluation. Results stored in
    profile_order_list — merged with order_list at merge_orders node.
    """
    signal_data: SignalData = state.get("signal_data")
    market_data: MarketData = state.get("market_data")

    if not signal_data or not market_data:
        return {"profile_order_list": []}

    market_summary = _build_market_summary(state)
    input_vars = {
        "ticker":           signal_data.ticker,
        "romour_summary":   signal_data.rumor_summary,
        "credibility":      signal_data.credibility,
        "credibility_reason": signal_data.credibility_reason,
        "trade_signal":     signal_data.trade_signal,
        "confidence":       signal_data.confidence,
        "trade_rationale":  signal_data.trade_rationale,
        "market_summary":   market_summary,
    }

    # ── Fetch CUSTOM accounts ─────────────────────────────────────────────────
    custom_accounts = await fetch_accounts_by_profile(RiskProfile.CUSTOM)
    if not custom_accounts:
        print("   [🎯 Profile:custom] No custom accounts — skipping")
        return {"profile_order_list": []}

    # ── Fetch agent settings + buying power per user concurrently ────────────
    user_ids = [acc["id"] for acc in custom_accounts]
    settings_list, bp_list = await asyncio.gather(
        asyncio.gather(*[_fetch_agent_settings(uid) for uid in user_ids]),
        asyncio.gather(*[fetch_buying_power(uid) for uid in user_ids]),
    )

    # ── Group users by (prompt, buying_power) to minimise LLM calls ──────────
    # Users with the same prompt AND same buying power share one LLM call.
    fallback = PROFILE_SYSTEM_PROMPTS[RiskProfile.CUSTOM]
    # group_key → {"prompt": str, "buying_power": float, "user_ids": [str]}
    groups: dict[tuple, dict] = {}

    for uid, settings, raw_bp in zip(user_ids, settings_list, bp_list):
        prompt = (settings.get("custom_prompt") or "").strip() or fallback
        bp = float(raw_bp) if isinstance(raw_bp, (int, float)) else 0.0
        if bp <= 0:
            print(f"   [⚠️ Profile:custom] Skipping user {uid} — buying power unavailable ({raw_bp})")
            continue
        key = (prompt, round(bp, 2))
        if key not in groups:
            groups[key] = {"prompt": prompt, "buying_power": bp, "user_ids": []}
        groups[key]["user_ids"].append(uid)

    print(f"   [🎯 Profile:custom] {len(custom_accounts)} user(s) | {len(groups)} unique (prompt+BP) group(s)")

    if not groups:
        return {"profile_order_list": []}

    # ── One LLM call per unique (prompt, buying_power) group ─────────────────
    group_list = list(groups.values())
    decisions = await asyncio.gather(*[
        _run_profile_llm(
            llm, RiskProfile.CUSTOM,
            {**input_vars, "buying_power": f"{g['buying_power']:,.2f}"},
            signal_data.ticker,
            system_prompt=g["prompt"],
        )
        for g in group_list
    ])

    # ── Build RiskAdjResult directly from LLM output — no risk layer ─────────
    results: list[RiskAdjResult] = []

    for group, decision in zip(group_list, decisions):
        if decision.action == TradeAction.HOLD:
            print(f"   [🎯 Profile:custom] group HOLD — skipping {len(group['user_ids'])} user(s)")
            continue

        risk_per_share   = abs(decision.entry_price - decision.stop_loss)
        reward_per_share = abs(decision.take_profit - decision.entry_price)
        actual_rr        = reward_per_share / risk_per_share if risk_per_share > 0 else 0.0
        bp               = group["buying_power"]

        metrics = RiskMetrics(
            risk_score       = decision.confidence,
            risk_per_share   = f"${risk_per_share:.2f}",
            reward_per_share = f"${reward_per_share:.2f}",
            actual_rr        = f"{actual_rr:.1f}:1",
            total_risk       = f"${decision.qty * risk_per_share:.0f} ({decision.qty * risk_per_share / bp * 100:.1f}% BP)" if bp > 0 else "N/A",
            suggested_qty    = f"{decision.qty:.0f}",
            near_resistance  = False,
            atr_distance     = "N/A",
            max_risk_5pct    = f"${bp * 0.02:.0f}",
        )
        assessment = RiskAssessment(
            risk_status    = "APPROVED",
            risk_score     = decision.confidence,
            adjusted_trade = decision,
            metrics        = metrics,
            issues         = [],
        )

        for user_id in group["user_ids"]:
            results.append(RiskAdjResult(
                user_id                = user_id,
                profile                = RiskProfile.CUSTOM,
                adjusted_order_details = decision,
                risk_evaluation        = assessment,
                should_execute         = decision.qty > 0,
                conflict_resolution    = {},
            ))

    standard = state.get("standard_order_list") or []
    combined = [*standard, *results]
    should_execute = any(o.get("should_execute", False) for o in combined)

    print(f"   [🎯 Profile Reasoning] standard={len(standard)} | custom={len(results)} | should_execute={should_execute}")
    return {
        "order_list":     combined,
        "should_execute": should_execute,
    }
