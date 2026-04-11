# Trading Strategy & Decision Logic

## Overview
Agent M is a short-term swing trading agent (typically a 2–5 day horizon) designed to capture news-driven volatility. It focuses on how the market reacts to a catalyst rather than the news itself, allowing it to either fade overreactions or ride strong momentum breakouts.

---

## The Decision Pipeline
Every trade follows a strict path from a news signal to execution:
1.  **Signal Ingestion**: News or social media rumors are received and scored for credibility.
2.  **LLM Reasoning**: The "Brain" analyzes market data (RSI, MACD, Bollinger Bands, ATR, etc.) alongside the news to decide on an action: **BUY**, **SELL**, or **HOLD**.
3.  **Risk Adjustment**: The reasoning is passed through a risk layer that applies user-specific guardrails (Conservative vs. Aggressive profiles).
4.  **Execution**: Validated trades are placed via the Alpaca Brokerage API using bracket orders.

---

## LLM Reasoning Node
The reasoning node uses advanced technical indicators and catalyst analysis to classify the trade.

### Catalyst Classification
-   **STRONG**: High-impact events like earnings surprises, FDA decisions, M&A activity, or major regulatory rulings.
-   **WEAK**: Speculative rumors, analyst price target changes, or social media sentiment pieces.

### Price Action Classification
-   **Flush-and-recover**: A dip that was quickly bought up (do not fade).
-   **Spike-and-dump**: A surge that was quickly sold off (potential fade).
-   **Gap Detection**: If the price opens >1% above yesterday’s high, it’s treated as a high-conviction breakout.

### Technical Alignment (Conflict Check)
To prevent "yapping" and ensure accuracy, the LLM counts alignment factors:
-   **Strong catalysts** can trigger trades alone.
-   **Weak catalysts** require at least 3 factors (e.g., RSI extreme + candle direction + proximity to support/resistance).
-   **RSI Extremes**: RSI >90 or <15 counts as a double-weighted factor for technical fades.

---

## Level Calculation (Stop Loss & Take Profit)
Agent M calculates entry and exit levels based on market structure, not arbitrary math.

-   **Entry**:
    -   **At-market**: If the price is near a key level.
    -   **Anticipatory**: If RSI is extreme and the price is moving toward a structural level.
-   **Stop Loss (SL)**: Set just beyond the nearest support or resistance level (offset by ATR) to avoid "stop-hunting" volatility.
-   **Take Profit (TP)**: Set just before the next major structural target (SMA20, Bollinger Middle, or Resistance) to ensure fills before a potential reversal.

---

## Risk Adjustment Layer
After the LLM reasoning, the risk layer applies profile-specific gates:

1.  **Gate 1 (Penny Stocks)**: Blocks trades on stocks under $5 (configurable).
2.  **Gate 2 (Confidence)**: Minimum LLM confidence threshold (e.g., 70% for Conservative).
3.  **Gate 3 (Risk/Reward)**: Minimum RR ratio (e.g., 1.5:1 for Conservative).
4.  **Gate 4 (Risk Score)**: A final score incorporating confidence plus bonuses for technical alignment (MACD, RSI).

---

## Risk Profiles

| Feature | Conservative | Aggressive |
| :--- | :--- | :--- |
| **Max Risk per Trade** | 1% of buying power | 3% of buying power |
| **Max Position Size** | 3% of buying power | 6% of buying power |
| **Min Confidence** | 70% | 65% |
| **Min Risk/Reward** | 1.5 : 1 | 2.0 : 1 |
| **Stop Loss Cap** | 5% maximum | 10% maximum |
| **Take Profit Cap** | 12% maximum | 25% maximum |
| **Penny Stock Block** | Enabled | Disabled |
