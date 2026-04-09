# Trade Handling — Agent M

How a trade is decided, adjusted, and placed from signal to execution.

---

## 1. LLM Decision (Reasoning Node)

The LLM is given market data and news context and must produce a BUY, SELL, or HOLD decision.

### Prompt Structure
- **System**: Strategy rules, step-by-step analysis instructions, conflict check logic
- **Human**: Live market data block + news signal inputs

### Market Data Inputs Provided to LLM
| Field | Source |
|---|---|
| Current Price | Alpaca live broker quote |
| Candle type, body%, body-to-range ratio | Yahoo Finance (yesterday's OHLCV) |
| Range (Low–High), ATR14 | Yahoo Finance |
| 3D Range (high/low over 3 days) | Yahoo Finance |
| RSI | Yahoo Finance (14-period) |
| SMA20, SMA50, SMA200 | Yahoo Finance |
| MACD, Signal, Histogram | Yahoo Finance |
| BB Lower, Upper, Middle, Position% | Yahoo Finance (20-period, 2 std) |
| Support, Resistance | Yahoo Finance (30-day price history) |
| Bid, Ask, Spread | Alpaca live broker quote |

### News Signal Inputs
- News/rumor summary
- Catalyst credibility (STRONG / WEAK) + reason
- Initial signal direction from news aggregator
- Signal confidence score
- Signal rationale

> The initial signal is a starting point only. The LLM is instructed to validate or override it using market data — it must not inherit the signal's entry or exit levels.

---

## 2. LLM Analysis Steps (as instructed in prompt)

### Step 1 — Classify Catalyst
- **STRONG**: Earnings surprise, FDA decision, M&A, regulatory action, major legal ruling, institutional research from documented top-tier firm
- **WEAK**: Social media rumor, short-seller opinion, analyst price target change, sentiment piece, unverified report

### Step 2 — Classify Price Action
- **Flush-and-recover**: Closed near high, large range vs ATR → market rejected the move → do NOT fade
- **Spike-and-dump**: Closed near low, large range vs ATR → sellers in control → fade requires RSI/level confirmation
- **Gap above OHLCV High**: Current price >1% above yesterday's High → treat as breakout, not neutral

### Step 3 — Interpretation Rules
| Condition | Bias |
|---|---|
| Strong catalyst + breakout candle | Continuation |
| Weak catalyst + overextension above BB upper / resistance | Fade |
| Flush-and-recover + price near support | Mean reversion BUY |
| Spike-and-dump + price near resistance | Mean reversion SELL |
| Conflicting signals | HOLD |
| MACD bearish + bullish candle | Mixed → HOLD |
| MACD bullish + bearish candle at resistance + RSI >90 | RSI + price structure override MACD |
| RSI >90 + price at resistance + candle rejection | Three factors met — do not dismiss |

### Step 4 — Conflict Check
Count alignment factors before finalising:
- Catalyst quality (STRONG = continuation, WEAK on overextended = fade)
- Candle direction (bullish = BUY, bearish = SELL, neutral = 0)
- MACD histogram (positive = BUY, negative = SELL)
- RSI extreme (>75 = SELL, <30 = BUY; >90 or <15 counts **double**)
- Proximity to key level (within 2% of resistance for SELL, support for BUY)

**Threshold**: STRONG catalyst alone (count=1) is sufficient. WEAK catalyst requires ≥3 total factors.

---

## 3. Entry, SL, TP Calculation (LLM)

The LLM calculates all levels explicitly following this order:

### Step A — Identify Key Levels
From market data: Support, Resistance, BB Lower, BB Upper, BB Middle, SMA20, ATR14

### Step B — Entry Mode
| Mode | Condition | Entry |
|---|---|---|
| At-market | Current price within 0.5x ATR of key level | Current price |
| Anticipatory | RSI <20 (BUY) or >80 (SELL) AND price not yet at level AND level within 2x ATR | Key level itself |

If anticipatory level is >2x ATR away → fall back to at-market.

### Step C — Stop Loss
| Direction | Formula |
|---|---|
| BUY | Lower of (Support, BB Lower) − 0.25x ATR |
| SELL | Higher of (Resistance, BB Upper) + 0.25x ATR |

SL placed beyond structural level so normal volatility does not trigger it.

### Step D — Take Profit
| Direction | Formula |
|---|---|
| BUY | Nearest target above entry (Resistance, SMA20, BB Middle) − 0.15x ATR |
| SELL | Nearest target below entry (Support, SMA20, BB Middle) + 0.15x ATR |

TP stops short of the target so it fills before a natural reversal at that level.

### Step E — RR Verification
- `risk = abs(entry - stop_loss)`
- `reward = abs(take_profit - entry)`
- `RR = reward / risk`
- If RR < 2.0 → return HOLD (LLM-level gate)
- Thesis must state: `"risk=$X, reward=$X, RR=X:1"` explicitly

### LLM Output Format
```json
{
  "action": "BUY" | "SELL" | "HOLD",
  "confidence": 0.0-1.0,
  "entry_price": float,
  "stop_loss": float,
  "take_profit": float,
  "qty": float,
  "risk_reward": "X:1",
  "thesis": "...",
  "current_stock_price": float
}
```

### LLM Retry Logic
- Max 3 attempts (1 initial + 2 retries)
- Backoff: 1.5s, 3.0s
- `JSONDecodeError` raises and triggers retry (not silently swallowed)
- After all retries exhausted → default HOLD with `thesis: "LLM error - no trade"`

---

## 4. Risk Adjustment Layer

After the LLM returns BUY/SELL, the risk layer evaluates per-user across both profiles concurrently.

### Gate Order

**Gate 1 — Penny Stock**
- Block if `is_penny=True` AND profile has `penny_block=True` (conservative only)

**Gate 2 — Confidence**
- Block if `confidence < min_confidence` (0.70 conservative, 0.65 aggressive)

**Entry — Preserved**
- Risk layer does not override entry price
- Logs deviation % from current market price as informational only

**SL — Preserved with Hard Cap**
- SL from reasoning is kept as-is
- Hard cap enforced: SL cannot be >5% from entry (conservative) or >10% (aggressive)
- If SL breaches cap → adjusted to cap value

**Gate 3 — RR Check**
- `reasoning_rr = abs(take_profit - entry) / abs(entry - stop_loss)`
- If `reasoning_rr < profile.min_rr` → **block trade** (do not stretch TP)
- Conservative min: 1.5:1 | Aggressive min: 2.0:1

**TP — Preserved with Hard Cap**
- TP from reasoning is kept as-is (structural levels respected)
- Hard cap enforced: TP cannot be >12% from entry (conservative) or >25% (aggressive)
- If TP breaches cap → adjusted to cap value
- No stretching or pulling in based on RR math

**Position Sizing**
```
max_risk_dollars    = buying_power × max_risk_pct
max_position_dollars = buying_power × max_position_pct
qty_by_risk         = max_risk_dollars / risk_per_share
qty_by_position     = max_position_dollars / entry
qty                 = max(1, round(min(qty_by_risk, qty_by_position)))
```
- Conservative: 1% risk, 3% position
- Aggressive: 3% risk, 6% position

**Risk Scoring**
Start from LLM confidence, apply bonuses:
| Condition | Adjustment |
|---|---|
| RR ≥ 3.0 | +0.10 |
| RR ≥ 2.0 | +0.05 |
| RR < min_rr | −0.10 |
| MACD bearish (SELL) or bullish (BUY) | +0.05 |
| RSI >60 (SELL) or <40 (BUY) | +0.05 |
| Price within 1x ATR of key level | +0.05 |

Score clamped to [0.0, 1.0].

**Gate 4 — Risk Score**
- Block if `score < min_risk_score` (0.72 conservative, 0.62 aggressive)

**Conflict Resolution**
- Checks for existing opposing position or pending orders on same ticker per user
- Auto-resolves: closes conflicting positions, cancels pending orders
- If conflict exists and position open → skip execution for that user

### Multi-User Execution
- All users fetched by profile (`/decisions/trading-accounts/aggressive|conservative`)
- Risk evaluated concurrently for all users across both profiles
- `should_execute = True` if **any** user passes — not all-or-nothing

---

## 5. Order Execution

Orders placed via `POST /orders/bracket` on the trading service.

### Order Type Logic
| Condition | Entry Type |
|---|---|
| `entry_price` is set | Limit order at `entry_price` |
| No `entry_price` | Market order |

### Bracket Order Payload
```json
{
  "symbol": "TICKER",
  "side": "buy" | "sell",
  "qty": float,
  "entry_type": "limit" | "market",
  "entry_price": float,
  "take_profit_price": float,
  "stop_loss_price": float,
  "time_in_force": "gtc"
}
```

All price fields rounded to 2 decimal places before submission.

### Execution Result States
| Status | Meaning |
|---|---|
| `executed` | Order placed, `order_id` returned |
| `failed` | API returned non-200 |
| `timeout` | Request exceeded 10s |
| `skipped` | Blocked by conflict resolution |

All users executed concurrently via `asyncio.gather`.

---