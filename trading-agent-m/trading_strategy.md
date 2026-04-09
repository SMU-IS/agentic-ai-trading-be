# Trading Agent M — Strategy Documentation

## Overview

Agent-M is a short-term swing trading agent (2–5 day horizon) that trades news-driven volatility. It captures price overreactions to catalysts — fading parabolic moves or riding strong breakouts.

The unifying principle: **trade the reaction, not the story**. Every trade is triggered by how price responds to a catalyst, not by the news itself.

---

## Trading Strategies

Agent-M runs 3 distinct strategies depending on catalyst strength and price action:

### 1. Mean Reversion (Fade the Overreaction)
Targets stocks that have moved too far on weak news and are likely to snap back.
- Weak catalyst + parabolic overextension above BB upper / resistance → **SELL**
- Spike-and-dump candle + price near resistance → **SELL**
- Flush-and-recover candle + price near support → **BUY**

### 2. Momentum / Continuation
Rides the follow-through after a high-conviction catalyst. Does not fade strong moves.
- Strong catalyst + breakout candle → **BUY/SELL in direction of move**
- Gap above yesterday's High → treat as breakout, enter in gap direction

### 3. Exhaustion Short
Pure technical fade triggered by extreme RSI, independent of catalyst strength.
- RSI >90 + price at resistance + candle rejection → **SELL**
- RSI >90 counts double in the alignment check — treated as a strong standalone signal

### When to HOLD
- Conflicting signals across catalyst and price action classification
- MACD bearish but candle bullish (or vice versa) with no RSI extreme
- Weak catalyst with fewer than 3 alignment factors confirmed
- RR below 2.0 after calculating entry/SL/TP

**Pipeline:**
```
News Aggregator → Redis Signal Stream → Agent-M
→ Fetch Signal Data → Fetch Market Data → LLM Reasoning → Risk Adjustment → Execute
```

---

## Run Conditions

Agent-M only processes signals when **both** conditions are true:
- Redis flag `services:trading-agent-m → enabled = "true"` (or `"1"`, `"yes"`)
- Alpaca `/clock` returns `is_open: true`

Both are checked at startup and re-evaluated every 10 seconds via a poller.

---

## LLM Reasoning (Perplexity)

The brain node analyzes market data and news to produce a trade decision.

### Catalyst Classification
- **STRONG**: Earnings surprise, FDA decision, M&A, regulatory action, major legal ruling, institutional research
- **WEAK**: Social media rumor, speculative short-seller opinion, analyst price target change, unverified report

### Price Action Classification
- **Flush-and-recover**: Closed near high, large range vs ATR → market rejected the move → do not fade
- **Spike-and-dump**: Closed near low, large range vs ATR → sellers in control → fade with confirmation
- **Gap above OHLCV High**: Treat as breakout, not neutral

### Conflict Check (alignment factors)
- Catalyst quality (strong = continuation, weak on overextended = fade)
- Candle direction (bullish = BUY, bearish = SELL)
- MACD histogram (positive = BUY, negative = SELL)
- RSI extreme (>75 = SELL, <30 = BUY; >90 or <15 counts double)
- Proximity to key level (within 2% of resistance for SELL, support for BUY)

A STRONG catalyst alone (count = 1) is sufficient. A WEAK catalyst requires ≥3 total factors.

### Entry Pricing
- **At-market**: Current price within 0.5x ATR of key level → entry = current price
- **Anticipatory**: RSI <20 (BUY) or >80 (SELL), price not yet at structural level → entry = key level, must be within 2x ATR

### SL/TP Rules (from LLM)
- **SL (BUY)**: Below support or BB lower − 0.25x ATR
- **SL (SELL)**: Above resistance or BB upper + 0.25x ATR
- **TP (BUY)**: Nearest target above entry (resistance, SMA20, BB middle) − 0.15x ATR
- **TP (SELL)**: Nearest target below entry (support, SMA20, BB middle) + 0.15x ATR
- Minimum RR of 2.0 required from LLM, else return HOLD

### Retry Logic
- Max 2 retries on LLM/parse failure with 1.5s backoff
- JSON parse failure raises exception (triggers retry)
- Fallback to HOLD after all retries exhausted

---

## Risk Profiles

| Parameter | Conservative | Aggressive |
|---|---|---|
| Penny stock block | Yes | No |
| Min confidence | 70% | 65% |
| Min RR | 1.5:1 | 2.0:1 |
| Max SL from entry | 5% | 10% |
| Max TP from entry | 12% | 25% |
| Max risk per trade | 1% of buying power | 3% of buying power |
| Max position size | 3% of buying power | 6% of buying power |
| Min risk score | 0.72 | 0.62 |

---

## Risk Layer Logic (Gate Order)

1. **Gate 1 — Penny stock**: Block if price qualifies as penny AND profile has `penny_block=True`
2. **Gate 2 — Confidence**: Block if LLM confidence below profile minimum
3. **Entry**: Preserved from reasoning — risk layer does not override entry
4. **SL**: Preserved from reasoning — only enforced against hard % cap
5. **Gate 3 — RR check**: Block if `reasoning_rr < profile.min_rr` — trade rejected, TP not stretched
6. **TP hard cap**: Only override if TP exceeds the max % from entry
7. **Position sizing**: `qty = min(max_risk_dollars / risk_per_share, max_position_dollars / entry)`, floored at 1
8. **Risk scoring**: Start from confidence, add bonuses for RR, MACD alignment, RSI alignment, proximity to key level
9. **Gate 4 — Risk score**: Block if `score < profile.min_risk_score`

### Conflict Resolution
Before execution, checks for opposing positions or pending orders on the same ticker. Auto-resolves by closing/cancelling conflicts. If conflict exists and position is open, trade is skipped for that user.

---

## Execution

- Bracket orders via `POST /orders/bracket`
- `entry_type`: limit if entry_price set, else market
- `time_in_force`: GTC
- All users across both profiles executed concurrently

---

## Redis Architecture

- **Consumer group**: `trading-agent-m-group` on `trading_signal_stream`
- **Consumer name**: `trading-agent-m` (shared across instances — Redis group guarantees at-most-once delivery)
- **ACK policy**: `xack` + `xdel` only on workflow success — failures stay in PEL for retry
- **On workflow failure**: message stays in PEL, no ack, no delete

---

## Changelog

### 2026-04-10
- **TP logic overhaul**: Risk layer no longer extends or pulls in TP to hit profile RR targets. LLM's structurally-derived TP is now preserved as-is. If `reasoning_rr < min_rr`, trade is **blocked** instead of TP being stretched. Hard % cap (12%/25%) remains as the only override.
- **Removed**: Post-adjustment Gate 3 RR check (redundant after early block on `reasoning_rr`)
- **Rationale**: LLM sets TP at structural levels (support, resistance, SMA). Overriding by RR math displaced TP to arbitrary prices with no natural fill magnet. Stretching TP to meet minimum RR pushed targets past intended structure, reducing fill probability.

### 2026-04-10
- **Redis consumer group**: Migrated from `xread` + `xdel` to `xreadgroup` + `xack` + `xdel` on `trading_signal_stream`
- **Race condition fix**: Multiple instances previously could read and process the same message simultaneously. Consumer group atomically claims messages at the Redis level, guaranteeing at-most-once delivery per message across all instances.
- **ACK on success only**: `xack` + `xdel` moved to after `workflow.run()` succeeds. Failures leave message in PEL for retry rather than silently discarding.
- **JSON parse fix**: `parse_llm_json` previously swallowed `JSONDecodeError` and returned a fallback, preventing the retry loop from ever retrying on parse failures. Now raises, triggering the retry backoff.

### 2026-04-10
- **Startup run condition fix**: Initial `service_enabled` seed previously checked only the Redis flag, ignoring market hours. A signal received in the first 10s after startup could be processed even when market was closed. Fixed to apply the same AND condition (Redis flag + market open) at startup.
- **Vol ratio**: Removed intraday session progress projection (`_session_progress_from_clock`). `vol_ratio` now uses raw daily volume from yfinance without adjustment.
