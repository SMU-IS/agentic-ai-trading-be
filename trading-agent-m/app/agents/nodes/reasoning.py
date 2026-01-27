# async def node_decide_trade(self, state: AgentState):
#     """
#     Brain: Uses Ollama to decide on the trade.
#     """

#     print(
#         f"   [🧠 LLM Brain] Analyzing {state['ticker']} for {state['user_id']}..."
#     )

#     # 1. Prompt
#     prompt = ChatPromptTemplate.from_messages(
#         [
#             (
#                 "system",
#                 """You are a Portfolio Manager.
#             Analyse the following market signal and portfolio status.

#             DECISION RULES:
#             - BUY if sentiment is bullish (score > 0.7) and risk is aggressive.
#             - SELL if sentiment is bearish (score < 0.3) and we own the stock.
#             - HOLD otherwise.

#             Return ONLY a JSON object in this format:
#             {{ "action": "BUY", "qty": 5, "reason": "Sentiment is strong" }}
#             """,
#             ),
#             (
#                 "human",
#                 """
#             Ticker: {ticker}
#             Signal: {signal}
#             Portfolio: {portfolio}
#             Risk Profile: {risk_profile}
#             """,
#             ),
#         ]
#     )

#     # 2. Invoke Ollama
#     chain = prompt | self.llm
#     response = await chain.ainvoke(
#         {
#             "ticker": state["ticker"],
#             "signal": state["signal"],
#             "portfolio": state["portfolio"],
#             "risk_profile": state["risk_profile"],
#         }
#     )

#     # 3. Parse JSON Output
#     try:
#         content = response.content.strip()

#         if "```json" in content:
#             content = content.split("```json")[1].split("```")[0].strip()
#         elif "```" in content:
#             content = content.split("```")[1].split("```")[0].strip()

#         decision = json.loads(content)

#     except json.JSONDecodeError:
#         print(f"❌ Failed to parse JSON from LLM: {response.content}")
#         decision = {"action": "HOLD", "qty": 0, "reason": "JSON Parse Error"}

#     return {
#         "action": decision.get("action", "HOLD"),
#         "order_details": {"ticker": state["ticker"], "qty": decision.get("qty", 0)},
#         "should_execute": decision.get("action") in ["BUY", "SELL"],
#         "reasoning": decision.get("reason", "No reason provided"),
#     }

import json

from app.agents.state import AgentState
from langchain_core.prompts import ChatPromptTemplate


async def node_decide_trade(llm, state: AgentState):
    """
    Brain: Uses LLM for short-term swing trades driven by news volatility.
    Goal: Capture 2-5 day swings against short-term news-driven volatility.
    """
    print(
        f"   [🧠 Swing Trading Brain] Analyzing {state['ticker']} for {state['user_id']}..."
    )

    def get_market_summary(state: AgentState) -> str:
        """Safe market data extraction."""
        market = state.get('market_data', {})
        print(f"   [📈 Market Data] {market.get('yahoo', {})}")
        return json.dumps(market)
        
    market_summary = get_market_summary(state)
    # print(f"   [📈 Market Data] {market_summary}")
    # Enhanced prompt for news-driven swing trading
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """You are an expert short-term swing trader (2-5 day horizon) specializing in news-driven volatility.

            STRATEGY: Capture short-term swings from news sentiment shocks. Trade against overreactions.

            CRITERIA FOR SWING TRADES:
            1. NEWS IMPACT: Strong sentiment shift (>0.4 absolute score) OR high-impact event (earnings, downgrade, etc.)
            2. TECHNICAL CONFIRMATION:
            - BUY: Price near support, RSI < 40 (oversold), bullish divergence
            - SELL: Price near resistance, RSI > 70 (overbought), bearish divergence
            3. VOLATILITY: ATR > 20-day average (swing opportunity exists)
            4. REGIME: Avoid if VIX > 25 (too chaotic for swings)

            POSITION SIZING & RISK:
            - Entry: Market or pullback to key level
            - SL: 1.5x ATR from entry (volatility-adjusted)
            - TP: 2.5x ATR from entry (2:1 R:R minimum)
            - Max risk: 1% account per trade

            EXISTING POSITIONS:
            - If you own it and news turns against: Scale out 50-100%
            - Never add to losers

            IGNORE if:
            - Weak news (<0.3 sentiment score)
            - No technical confirmation
            - Poor R:R (< 1.5:1)

            Return ONLY valid JSON. Never return invalid trades.
            """,
            ),
            (
                "human",
                """
            Below is the latest market data:
            Alpaca is the brokerage data, Yahoo provides recent historicals.
            Based on these data given, you are to make entry/exit decisions.
            {market_summary}

            NEWS SIGNAL:
            Sentiment: {sentiment} (score: {score})
            Event Type: {event_type}
            Historical Context: {historical_context}

            PORTFOLIO:
            {portfolio}

            RISK PROFILE: {risk_profile}

            ANALYSIS REQUIRED:
            1. News impact assessment
            2. Technical setup (support/resistance, RSI, momentum)
            3. Volatility regime (swing viable?)
            4. Entry/SL/TP calculation (ATR-based)
            5. Position sizing
            6. Clear thesis (why this swing works)

            Return JSON:
            {{
            "action": "BUY" | "SELL" | "HOLD",
            "confidence": 0.0-1.0,
            "entry_price": float,
            "stop_loss": float,
            "take_profit": float,
            "qty": float,
            "risk_reward": "X:1",
            "thesis": "Detailed reasoning with news + technical justification (also provide figures from market data to support your entry and exit leveels)"
            }}
            """,
            ),
        ]
    )

    # 2. Prepare enriched input for LLM
    input_vars = {
        "ticker": state["ticker"],
        "current_price": state["signal"].get("current_price", 150.0),  # fallback
        "atr": state["signal"].get("atr", 3.0),  # fallback 14-period ATR
        "sentiment": state["signal"].get("sentiment", "neutral"),
        "score": state["signal"].get("score", 0.0),
        "event_type": state["signal"].get("event_type", "general"),
        "historical_context": state.get("historical_context", []),
        "portfolio": state["portfolio"],
        "risk_profile": state["risk_profile"],
        "market_summary": market_summary
    }

    # 3. Invoke LLM
    chain = prompt | llm
    response = await chain.ainvoke(input_vars)

    # 4. Parse enhanced JSON
    try:
        content = response.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        decision = json.loads(content)

        # Validate required fields
        if decision.get("action") not in ["BUY", "SELL", "HOLD"]:
            decision["action"] = "HOLD"

    except json.JSONDecodeError:
        print(f"❌ LLM JSON parse failed: {response.content[:200]}...")
        decision = {
            "action": "HOLD",
            "confidence": 0.0,
            "entry_price": 0.0,
            "stop_loss": 0.0,
            "take_profit": 0.0,
            "qty": 0.0,
            "risk_reward": "0:1",
            "thesis": "JSON parsing error - no trade",
        }

    # 5. Return structured state update
    return {
        "action": decision.get("action", "HOLD"),
        "order_details": {
            "ticker": state["ticker"],
            "side": decision.get("action", "HOLD"),
            "qty": float(decision.get("qty", 0)),
            "entry_price": float(decision.get("entry_price", 0)),
            "stop_loss": float(decision.get("stop_loss", 0)),
            "take_profit": float(decision.get("take_profit", 0)),
        },
        "should_execute": decision.get("action") in ["BUY", "SELL"]
        and decision.get("confidence", 0) > 0.6,
        "reasoning": decision.get("thesis", "No reasoning provided"),
        "confidence": decision.get("confidence", 0.0),
        "risk_reward": decision.get("risk_reward", "0:1"),
    }
