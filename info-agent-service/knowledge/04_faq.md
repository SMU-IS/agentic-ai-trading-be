# Frequently Asked Questions (FAQ)

## General Information
### What is Agent M and who is it for?
Agent M is a fully autonomous investment companion for retail investors. it translates financial news and internet sentiment into personalized buy/sell decisions executed via the **Alpaca Brokerage API**.

## Practical Usage
### How does the system help retail investors?
It solves information overload. By automatically scraping news and analyzing sentiment, it either answers user queries via a RAG chatbot or executes trades within pre-set risk limits.

## Decision Making
### How does the Trading Agent decide when to buy or sell?
The agent uses a pipeline: Scraped posts are checked for credibility, analyzed via FinBERT for sentiment, and then checked against user-set risk guardrails. Orders are only executed if the weighted sentiment score meets the threshold.

## Interactive Features
### Do I need an order ID to ask why a trade was made?
No. You can ask naturally, like "Why did you sell GOOGL last week?" Agent M will automatically search your last 30 days for matching trades and ask for clarification if multiple matches are found. You can even refer to items in a list, like "the first one."

## Reliability
### How do you ensure the accuracy of trade decisions?
We utilize multiple validation rounds, modular scrapers to prevent anti-bot blocking, and RAG-based validation to cross-reference news claims before they reach the execution engine.

## Trading Strategy Deep-Dive
### What is the difference between the Conservative and Aggressive risk profiles?
The **Conservative** profile is built for safety: it blocks penny stocks, requires higher LLM confidence (70%), accepts a lower risk/reward (1.5:1) to ensure more frequent exits, and limits risk to 1% of buying power per trade. The **Aggressive** profile allows penny stocks, requires 65% confidence, demands a 2.0:1 risk/reward, and risks up to 3% per trade.

### How are Stop Loss and Take Profit levels calculated?
Unlike simple percentage-based bots, Agent M uses **market structure**. The LLM identifies key levels like Support, Resistance, and moving averages. Stop Loss is placed just beyond these levels (using ATR for a buffer), and Take Profit is placed just before a target to ensure it fills during a fast move.

### What happens when technical signals conflict?
Agent M uses an **alignment check**. A strong catalyst (like earnings) can trigger a trade alone. However, weak news requires at least three technical factors to align (e.g., RSI extreme, candle shape, and support/resistance proximity). If factors conflict (like MACD bullish but candle bearish), the agent will default to a **HOLD**.

### How does Agent M handle "Gaps" and extreme RSI?
Agent M is programmed to recognize high-aura market moves. A **Gap** (opening >1% above yesterday's high) is treated as a breakout continuation. **RSI >90** is treated as an extreme exhaustion signal that can trigger a technical "fade" (short) even if the news seems positive, as the move is likely overextended.
