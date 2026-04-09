## Changelog for strategy
## reasoning + risk_adjust

### 2026-04-10 — TP Logic Overhaul
**What changed**: Risk layer no longer stretches or pulls in TP to meet profile RR targets.

**Before**: Risk layer recalculated TP from SL distance × target RR, overriding the LLM's structurally-derived level. If reasoning RR was below minimum, TP was extended further. If above maximum, TP was pulled in.

**After**: LLM's TP is preserved as-is. If `reasoning_rr < profile.min_rr`, the trade is **blocked** outright instead of TP being stretched. The only override remaining is the hard % cap (12%/25%).

**Why**: LLM sets TP at structural levels (support, resistance, SMA). Overriding by RR math displaced TP to arbitrary prices with no natural price magnet — reducing fill probability and bypassing the LLM's structural analysis. Stretching TP past intended structure made fills less likely before reversal.

---

### 2026-04-10 — Conservative min_rr Lowered
**What changed**: Conservative profile `min_rr` changed from `2.0` to `1.5`.

**Why**: Combined with the new block-not-stretch policy, a 2.0 minimum was too restrictive. The LLM already gates at 2.0 internally, but lowering the risk layer minimum to 1.5 reduces duplicate blocking and allows the risk score gate to make the final call.

---

### 2026-04-10 — RR Gate Moved Earlier
**What changed**: Removed post-adjustment Gate 3 RR check. RR is now evaluated on `reasoning_rr` before any adjustments, and blocks immediately if below minimum.

**Why**: The old gate checked `actual_rr` after TP had already been adjusted by the layer — meaning it was checking the layer's own math, not the original trade's validity. Moving the check to `reasoning_rr` (the LLM's unadjusted values) makes the gate meaningful.

---

### 2026-04-10 — LLM JSON Parse Fix
**What changed**: `parse_llm_json` previously caught `JSONDecodeError` and returned a HOLD fallback silently. Now it re-raises the exception.

**Why**: The retry loop in the reasoning node only retried on exceptions. Silently returning a fallback bypassed all retries — parse failures never triggered a second LLM call. Now parse failures propagate up and trigger the retry backoff (1.5s, 3.0s).

---

### 2026-04-10 — Prompt: RSI Above 90 Rule
**What changed**: Added explicit instruction that RSI >90 is an exceptional exhaustion signal and counts double. Added rule that RSI >90 + price at resistance + candle rejection = three alignment factors on their own.

**Why**: LLM was previously dismissing RSI >90 as "just one vote" among many signals. The intent is that extreme RSI exhaustion is a strong standalone signal that should not be overridden by a conflicting MACD.

---

### 2026-04-10 — Prompt: MACD Override Rule
**What changed**: Added rule — MACD bullish but candle bearish at resistance with RSI >90 → RSI and price structure override MACD. Count candle and RSI as aligned, MACD not counted.

**Why**: MACD is a lagging indicator. At extremes (RSI >90, price at resistance, rejection candle), current price structure outweighs MACD momentum. LLM was previously holding on these setups due to MACD conflict.

---

### 2026-04-10 — Prompt: Gap Detection Rule
**What changed**: Added instruction — if current price is >1% above yesterday's OHLCV High, treat as a breakout in the direction of the gap. Do not classify as neutral.

**Why**: Gaps are high-conviction directional moves. Classifying them as neutral caused LLM to miss clean continuation setups on gap-up/gap-down opens.

---

### 2026-04-10 — Vol Ratio Simplified
**What changed**: Removed `_session_progress_from_clock` intraday projection. `vol_ratio` now uses raw daily volume from yfinance without session progress adjustment.

**Before**: `vol_ratio = (raw_volume / pct_session_elapsed) / vol_avg20` — projected intraday volume to a full-session estimate.

**After**: `vol_ratio = volume / vol_avg20` — plain ratio using whatever yfinance returns.

**Why**: Clock-based projection added complexity and a dependency on Alpaca clock data in the Yahoo client. The vol gate was removed from risk profiles (`min_vol_ratio = 0.0`) so the projection was unused anyway.
