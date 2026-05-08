"""
Multi-profile reasoning node.

Replaces the separate reasoning.py + profile_reasoning.py pair with a single node
that runs profile-specific LLM calls for all active accounts in one step.

Profile handling:
  AGGRESSIVE  — hardcoded prompt, one LLM call shared across all aggressive users
  CONSERVATIVE — hardcoded prompt, one LLM call shared across all conservative users
  CUSTOM      — user's custom_prompt from DB, grouped by unique prompt text

Output: {"profile_decisions": list[ProfileDecision]}

Downstream:
  - AGGRESSIVE / CONSERVATIVE → risk_adjust applies hardcoded ProfileParams gates + position sizing
  - CUSTOM                    → risk_adjust applies user's own risk_settings from agent settings
"""

import asyncio
from typing import List, Literal
from typing_extensions import TypedDict, NotRequired

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

from app.agents.state import (
    AgentState, RiskProfile, SignalData,
    TradingDecision, TradeAction,
)
from app.agents.nodes.risk_adjust import fetch_accounts_by_profile, fetch_buying_power
from app.agents.llm_factory import get_llm


# ── Profile system prompts ────────────────────────────────────────────────────

AGGRESSIVE_SYSTEM_PROMPT = """You are an expert short-term swing trader (2-5 day horizon) specializing in news-driven volatility.

STRATEGY: Capture short-term swings from news sentiment shocks. Trade against overreactions.
You do NOT invest long term.
You do NOT speculate without catalysts.
You trade reactions not stories.


STEP 1 - CLASSIFY THE CATALYST:
A catalyst is STRONG if it is: earnings surprise, FDA decision, M+A announcement, regulatory action, major legal ruling, or institutional research from a top-tier firm with documented track record.
A catalyst is WEAK if it is: social media rumor, speculative short-seller opinion, analyst price target change, sentiment piece, or unverified report.
Label it clearly before proceeding.


STEP 2 - CLASSIFY TODAY'S PRICE ACTION:
Use the Candle type, Range (Low-High), and 3D Range from market data.
If the candle closed near its high and the range is large relative to ATR14, price RECOVERED (flush-and-recover).
If the candle closed near its low and the range is large relative to ATR14, price SOLD OFF (spike-and-dump).
A flush-and-recover means the news shock was absorbed intraday — the market rejected the move. Do not fade a move that already reversed.
A spike-and-dump means sellers took control. Fade requires further confirmation from RSI and key levels.
If the live Current Price (from broker) is more than 1% above the OHLCV High shown in Range, the stock has gapped above yesterday's candle. Treat this as a breakout in the direction of the gap. Do not classify it as neutral.


STEP 3 - APPLY INTERPRETATION RULES (only after Steps 1-2):
Strong catalyst + breakout candle = continuation bias
Weak catalyst + parabolic overextension above BB upper or resistance = fade bias
Flush-and-recover candle + price near support = mean reversion BUY
Spike-and-dump candle + price near resistance = mean reversion SHORT
Any conflicting signals across Steps 1-2 = HOLD. Do not force a trade.
RSI below 70 and price not at resistance = no overbought confirmation, do not short on thesis alone.
RSI above 90 is an exceptional exhaustion signal. RSI above 90 + price at or near resistance + candle rejection = three alignment factors met on their own. Do not dismiss RSI above 90 as just one vote among equals.
MACD bearish but candle bullish = mixed signal = HOLD.
MACD bullish but candle bearish at resistance with RSI above 90 = RSI and price structure override MACD. Count candle and RSI as aligned, not MACD.


STEP 4 - CONFLICT CHECK (run before finalizing):
Only return HOLD for a direct contradiction: SELL with a bullish candle closed near its high, or BUY with a bearish candle closed near its low.
Count each of the following as one alignment factor:
- Catalyst quality: a STRONG catalyst supports continuation. A WEAK catalyst on an overbought or overextended stock supports a fade. Count if direction matches proposed action.
- Candle direction: use the Candle field. Bullish candle supports BUY. Bearish candle supports SELL. Neutral = 0.
- Momentum (MACD): use the Histogram value. Positive histogram supports BUY. Negative supports SELL. Opposing does not block unless it is the only signal.
- RSI extreme: use the RSI value. Above 75 for SELL counts. Below 30 for BUY counts. Above 90 or below 15 counts double. The label (OVERBOUGHT/OVERSOLD/NEUTRAL) in the market data is for reference — always use the actual RSI number.
- Proximity to key level: use Support and Resistance from MARKET STRUCTURE. Current Price within 2% of Resistance for SELL counts. Within 2% of Support for BUY counts.
Tally the count in your thesis.
A STRONG catalyst alone (count = 1) is sufficient to proceed if there are no direct contradictions.
A WEAK catalyst requires at least 2 additional confirming factors (total >= 3) before proceeding.
Do not block a speculative trade on a STRONG catalyst simply because technicals are neutral.


Return ONLY valid JSON. Never return invalid trades.


ANALYSIS REQUIRED:
1. Catalyst classification (STRONG or WEAK, and why)
2. Price action classification (flush-and-recover, spike-and-dump, or neutral)
3. Conflict check result (how many alignment factors are confirmed)
4. Entry type determination (at-market or anticipatory — see rules below)
5. Entry/SL/TP levels built from key levels and ATR14
6. Position size (max qty 10)
7. Thesis explaining why the trade is valid or why it is a HOLD


ENTRY PRICING RULES:
Follow these steps in order. Do not skip steps or estimate — calculate each value explicitly.

STEP A — IDENTIFY KEY LEVELS:
From MARKET STRUCTURE: Support, Resistance.
From TECHNICAL INDICATORS: BB Lower, BB Upper, BB Middle, SMA20.
ATR14 comes from the Range line. Use the exact dollar value shown.

STEP B — CHOOSE ENTRY MODE:
AT-MARKET: use when Current Price is within 0.5 x ATR14 of the key level (Support for BUY, Resistance for SELL). Entry = Current Price.
ANTICIPATORY: use when RSI is below 20 (BUY) or above 80 (SELL) AND Current Price has not yet reached the structural level. Entry = the key level itself. Must be within 2 x ATR14 of Current Price, otherwise use AT-MARKET.

STEP C — SET STOP LOSS:
For BUY: SL = invalidation level (lower of Support or BB Lower) minus 0.25 x ATR14.
For SELL: SL = invalidation level (higher of Resistance or BB Upper) plus 0.25 x ATR14.
SL sits beyond the structural level so normal volatility does not trigger it.

STEP D — SET TAKE PROFIT:
For BUY: TP = nearest target above entry (Resistance, SMA20, or BB Middle) minus 0.15 x ATR14.
For SELL: TP = nearest target below entry (Support, SMA20, or BB Middle) plus 0.15 x ATR14.
TP stops short of the target so the order fills before a natural reversal at that level.

STEP E — VERIFY RISK/REWARD:
Calculate: risk = abs(entry - stop_loss), reward = abs(take_profit - entry), RR = reward / risk.
Show this calculation explicitly in the thesis: "risk=$X, reward=$X, RR=X:1".
If RR is below 2.0, the trade does not have a valid setup — return HOLD.
Do not round or inflate the RR figure. Use the exact calculated value.
"""


CONSERVATIVE_SYSTEM_PROMPT = """You are a conservative short-term swing trader (2-5 day horizon). Capital preservation is your first priority.

GOAL: Only take clean, high-conviction setups. Missed trades cost nothing. Bad trades cost capital.
You do NOT hold long term. You do NOT trade on ambiguous signals. When in doubt, HOLD.

STEP 1 — CLASSIFY THE CATALYST:
STRONG: earnings surprise, FDA decision, M&A announcement, regulatory action, major legal ruling, or institutional research from a documented top-tier firm.
WEAK: social media rumour, speculative short-seller opinion, analyst price-target change, sentiment piece, or unverified report.

STEP 2 — CLASSIFY TODAY'S PRICE ACTION:
Use Candle type, Range (Low-High), and 3D Range.
If the candle closed near its high and range is large vs ATR14 → FLUSH-AND-RECOVER.
If the candle closed near its low and range is large vs ATR14 → SPIKE-AND-DUMP.
If Current Price is more than 1% above yesterday's High → GAP UP. Treat as breakout in gap direction.

STEP 3 — ENTRY GATE (stricter than standard):
STRONG catalyst: proceed only if at least 1 confirming factor is present (candle direction, RSI extreme, or proximity to key level).
WEAK catalyst: require ALL THREE of (RSI extreme + price at structural level + confirming candle). If any is missing, return HOLD.
Mixed signals (e.g. MACD bullish but candle bearish) → HOLD.

STEP 4 — CONFLICT CHECK:
Count alignment factors:
  - Catalyst quality matches direction
  - Candle direction matches
  - MACD histogram sign matches
  - RSI extreme (>75 for SELL, <30 for BUY; above 90 or below 15 counts double)
  - Price within 2% of key level

Tally the count in the thesis. If below the threshold for the catalyst type → HOLD.

ENTRY RULES:
  No penny stocks (is_penny = YES → HOLD).
  SL buffer: 0.15 x ATR14 beyond the structural invalidation level (tighter than standard).
  TP: nearest structural target, pulled 0.10 x ATR14 short.
  Minimum RR: 2.5:1. Return HOLD if not achievable with the tight SL.
  Max qty: 5 shares.
  AT-MARKET only. ANTICIPATORY only when RSI < 15 (BUY) or > 90 (SELL).

Show the RR calculation explicitly in the thesis: "risk=$X, reward=$X, RR=X:1".

Return ONLY valid JSON. No comments. No special characters in thesis. Err toward HOLD on any ambiguity."""


# ── Shared human template ─────────────────────────────────────────────────────

HUMAN_TEMPLATE = """MARKET DATA FOR {ticker}:
All fields below are present. Do not state that any field is unavailable or missing.

Field reference:
- Current Price: latest Yahoo price (use this as current_stock_price)
- Candle: yesterday's OHLCV candle type, body%, body-to-range ratio
- Range: yesterday's Low - High, ATR14 (14-day average true range in dollars)
- RSI: momentum oscillator 0-100. OVERBOUGHT label = above 75. OVERSOLD label = below 30.
- SMA20 / SMA50 / SMA200: simple moving averages — use for trend direction and TP targets
- MACD / Signal / Histogram: histogram positive = bullish momentum, negative = bearish
- BB Lower / Upper / Position%: Bollinger Bands. Position 0% = at lower band, 100% = at upper band
- Support / Resistance: structural levels from 30-day price history — use as SL/TP anchors
- 3D Range: highest high and lowest low over last 3 days

{market_summary}

---

Ticker: {ticker}
News Summary: {romour_summary}
Catalyst Credibility: {credibility} ({credibility_reason})
Initial Signal Direction: {trade_signal}
Signal Confidence: {confidence}
Signal Rationale: {trade_rationale}

NOTE: Derive your own entry, SL, and TP from current price and ATR. Do not inherit the signal's levels.

UNIVERSAL RULES:
For SELL: stop_loss above entry, take_profit below entry.
For BUY: stop_loss below entry, take_profit above entry.
No special characters in thesis. If no valid trade, set action to HOLD with qty 0."""


# ── Structured output schema ──────────────────────────────────────────────────

class TradingDecisionSchema(BaseModel):
    action:              Literal["BUY", "SELL", "HOLD"]
    confidence:          float = Field(..., ge=0.0, le=1.0)
    entry_price:         float = Field(..., ge=0)
    stop_loss:           float = Field(..., ge=0)
    take_profit:         float = Field(..., ge=0)
    qty:                 float = Field(..., ge=0)
    risk_reward:         str   = Field(..., description="Format: X:1")
    thesis:              str
    current_stock_price: float = Field(..., ge=0)


# ── Output types ──────────────────────────────────────────────────────────────

class ProfileDecision(TypedDict):
    profile:             RiskProfile
    decision:            TradingDecision
    user_ids:            List[str]
    bypass_risk_adjust:  bool
    buying_power:        NotRequired[float]
    user_risk_settings:  dict  # {user_id: risk_settings_dict} for all profiles


# ── Market summary builder ────────────────────────────────────────────────────

def _build_market_summary(state: AgentState) -> str:
    if not state.get("market_data"):
        return "No market data available."
    y = state["market_data"].yahoo

    def _f(v, fmt=""):
        if v is None: return "N/A"
        try: return f"{v:{fmt}}"
        except: return str(v)

    rsi_label = "OVERSOLD" if y.rsi and y.rsi < 30 else "OVERBOUGHT" if y.rsi and y.rsi > 75 else "NEUTRAL"

    return f"""PRICE ACTION SUMMARY:
- Current Price: ${_f(y.current_price, '.3f')}
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
- Data Period: {y.period_summary}"""


def _hold(ticker: str) -> TradingDecision:
    return TradingDecision(
        action=TradeAction.HOLD, confidence=0.0, entry_price=0.0,
        stop_loss=0.0, take_profit=0.0, qty=0.0,
        risk_reward="0:1", thesis="Profile reasoning failed — defaulting to HOLD",
        current_stock_price=0.0, ticker=ticker,
    )


# ── LLM runner ────────────────────────────────────────────────────────────────

async def _run_llm(
    llm,
    system_prompt: str,
    input_vars: dict,
    profile: RiskProfile,
    ticker: str,
    max_retries: int = 2,
) -> TradingDecision:
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", HUMAN_TEMPLATE),
    ])
    structured_llm = llm.with_structured_output(TradingDecisionSchema)
    chain = prompt | structured_llm

    for attempt in range(max_retries + 1):
        try:
            output: TradingDecisionSchema = await chain.ainvoke(input_vars)
            decision = TradingDecision(
                action=TradeAction(output.action),
                confidence=output.confidence,
                entry_price=output.entry_price,
                stop_loss=output.stop_loss,
                take_profit=output.take_profit,
                qty=output.qty,
                risk_reward=output.risk_reward,
                thesis=output.thesis,
                current_stock_price=output.current_stock_price,
                ticker=ticker,
            )
            print(f"   [🧠 {profile.value}] attempt {attempt + 1} → action={decision.action} conf={decision.confidence:.0%}")
            return decision
        except Exception as e:
            print(f"   [⚠️  {profile.value}] attempt {attempt + 1} failed: {e}")
            if attempt < max_retries:
                await asyncio.sleep(1.5 * (attempt + 1))

    print(f"   [❌ {profile.value}] all retries exhausted — HOLD")
    return _hold(ticker)


# ── Agent-settings fetcher (custom profile) ───────────────────────────────────

async def _fetch_agent_settings(user_id: str) -> dict:
    import httpx
    from app.core.config import env_config
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{env_config.trading_service_url}/decisions/agent-settings/{user_id}"
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception as e:
        print(f"   [⚠️  custom] Failed to fetch settings for {user_id}: {e}")
    return {}


# ── Main node ─────────────────────────────────────────────────────────────────

async def node_profile_reasoning_v2(llm, state: AgentState) -> dict:
    """
    Unified multi-profile reasoning node.

    - Fetches all active accounts grouped by profile.
    - Runs one LLM call per profile group (preset) or per unique custom_prompt (custom).
    - Returns profile_decisions: list of ProfileDecision, consumed by risk_adjust and execute.
    """
    signal_data: SignalData = state.get("signal_data")
    if not signal_data or not state.get("market_data"):
        return {"profile_decisions": []}

    ticker        = signal_data.ticker
    market_summary = _build_market_summary(state)

    base_vars = {
        "ticker":             ticker,
        "romour_summary":     signal_data.rumor_summary,
        "credibility":        signal_data.credibility,
        "credibility_reason": signal_data.credibility_reason,
        "trade_signal":       signal_data.trade_signal,
        "confidence":         signal_data.confidence,
        "trade_rationale":    signal_data.trade_rationale,
        "market_summary":     market_summary,
        "buying_power_line":  "",  # overridden for custom
    }

    # ── 1. Fetch all accounts concurrently ───────────────────────────────────
    agg_accounts, cons_accounts, custom_accounts = await asyncio.gather(
        fetch_accounts_by_profile(RiskProfile.AGGRESSIVE),
        fetch_accounts_by_profile(RiskProfile.CONSERVATIVE),
        fetch_accounts_by_profile(RiskProfile.CUSTOM),
    )

    print(
        f"   [🧠 Reasoning] accounts — "
        f"aggressive={len(agg_accounts)} conservative={len(cons_accounts)} custom={len(custom_accounts)}"
    )

    # ── 2. Fetch agent settings + buying power for all users concurrently ────
    agg_user_ids    = [a["id"] for a in agg_accounts]
    cons_user_ids   = [a["id"] for a in cons_accounts]
    custom_user_ids = [a["id"] for a in custom_accounts]
    all_preset_ids  = agg_user_ids + cons_user_ids

    (
        preset_settings_list,
        custom_settings_list,
        custom_bp_list,
    ) = await asyncio.gather(
        asyncio.gather(*[_fetch_agent_settings(uid) for uid in all_preset_ids]),
        asyncio.gather(*[_fetch_agent_settings(uid) for uid in custom_user_ids]),
        asyncio.gather(*[fetch_buying_power(uid)    for uid in custom_user_ids]),
    )

    # {user_id: risk_settings_dict} for preset users
    preset_risk_settings: dict[str, dict] = {
        uid: (s.get("risk_settings") or {})
        for uid, s in zip(all_preset_ids, preset_settings_list)
    }

    tasks: list[asyncio.coroutine] = []
    task_meta: list[dict] = []

    # ── 3. Preset profiles ────────────────────────────────────────────────────

    if agg_accounts:
        tasks.append(_run_llm(llm, AGGRESSIVE_SYSTEM_PROMPT, base_vars, RiskProfile.AGGRESSIVE, ticker))
        task_meta.append({
            "profile":            RiskProfile.AGGRESSIVE,
            "user_ids":           agg_user_ids,
            "bypass_risk_adjust": False,
            "user_risk_settings": {uid: preset_risk_settings.get(uid, {}) for uid in agg_user_ids},
        })

    if cons_accounts:
        tasks.append(_run_llm(llm, CONSERVATIVE_SYSTEM_PROMPT, base_vars, RiskProfile.CONSERVATIVE, ticker))
        task_meta.append({
            "profile":            RiskProfile.CONSERVATIVE,
            "user_ids":           cons_user_ids,
            "bypass_risk_adjust": False,
            "user_risk_settings": {uid: preset_risk_settings.get(uid, {}) for uid in cons_user_ids},
        })

    # ── 4. Custom profiles (grouped by prompt + buying_power + model) ─────────

    custom_groups: dict[tuple, dict] = {}

    if custom_accounts:
        fallback_prompt = CONSERVATIVE_SYSTEM_PROMPT
        for uid, settings, raw_bp in zip(custom_user_ids, custom_settings_list, custom_bp_list):
            bp = float(raw_bp) if isinstance(raw_bp, (int, float)) else 0.0
            if bp <= 0:
                print(f"   [⚠️  custom] Skipping {uid} — buying power unavailable ({raw_bp})")
                continue
            prompt_text = (settings.get("custom_prompt") or "").strip() or fallback_prompt
            model_name  = (settings.get("llm_model") or "perplexity").lower()
            key = (prompt_text, round(bp, 2), model_name)
            if key not in custom_groups:
                custom_groups[key] = {
                    "prompt":             prompt_text,
                    "buying_power":       bp,
                    "model":              model_name,
                    "user_ids":           [],
                    "user_risk_settings": {},
                }
            custom_groups[key]["user_ids"].append(uid)
            custom_groups[key]["user_risk_settings"][uid] = settings.get("risk_settings") or {}

        for (prompt_text, bp, model_name), group in custom_groups.items():
            bp_line = f"\n- Available Buying Power: ${bp:,.2f}"
            vars_with_bp = {**base_vars, "buying_power_line": bp_line}
            group_llm = get_llm(model_name)
            tasks.append(
                _run_llm(group_llm, prompt_text, vars_with_bp, RiskProfile.CUSTOM, ticker)
            )
            task_meta.append({
                "profile":            RiskProfile.CUSTOM,
                "user_ids":           group["user_ids"],
                "bypass_risk_adjust": False,
                "buying_power":       bp,
                "model":              model_name,
                "user_risk_settings": group["user_risk_settings"],
            })

    if not tasks:
        print(f"   [🧠 Reasoning] No active accounts — skipping")
        return {"profile_decisions": []}

    # ── 5. Run all LLM calls concurrently ────────────────────────────────────
    print(f"   [🧠 Reasoning] {len(tasks)} LLM call(s) in flight...")
    decisions = await asyncio.gather(*tasks)

    # ── 6. Assemble ProfileDecision list ─────────────────────────────────────
    profile_decisions: list[ProfileDecision] = []

    for meta, decision in zip(task_meta, decisions):
        if decision.action == TradeAction.HOLD:
            print(
                f"   [🧠 {meta['profile'].value}] HOLD — "
                f"skipping {len(meta['user_ids'])} user(s)"
            )
            continue

        entry: ProfileDecision = {
            "profile":            meta["profile"],
            "decision":           decision,
            "user_ids":           meta["user_ids"],
            "bypass_risk_adjust": meta["bypass_risk_adjust"],
            "user_risk_settings": meta["user_risk_settings"],
        }
        if "buying_power" in meta:
            entry["buying_power"] = meta["buying_power"]

        profile_decisions.append(entry)
        print(
            f"   [🧠 {meta['profile'].value}] "
            f"action={decision.action} conf={decision.confidence:.0%} "
            f"entry=${decision.entry_price:.2f} users={len(meta['user_ids'])}"
        )

    print(f"   [🧠 Reasoning] {len(profile_decisions)} tradable group(s) produced")
    return {"profile_decisions": profile_decisions}
