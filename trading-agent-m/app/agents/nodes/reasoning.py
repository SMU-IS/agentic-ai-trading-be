# async def node_decide_trade(self, state: AgentState):
#     """
#     Brain: Uses Ollama to decide on the trade.
#     """

#     print(
#         f"   [🧠 LLM Brain] Analyzing {state['ticker']} ..."
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
import re

from app.agents.state import AgentState
from langchain_core.prompts import ChatPromptTemplate


async def node_decide_trade(llm, state: AgentState) -> AgentState:
    """
    Brain: Uses LLM for short-term swing trades driven by news volatility.
    Goal: Capture 2-5 day swings against short-term news-driven volatility.
    """
    print(
        f"   [🧠 Swing Trading Brain] Analyzing {state['ticker']}..."
    )

    def get_market_summary(state: AgentState) -> str:
        """Safe market data extraction."""
        market = state.get('market_data', {})
        return json.dumps(market)
        
    market_summary = get_market_summary(state)

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

            IGNORE if:
            - Weak news (<0.3 sentiment score)
            - No technical confirmation
            - Poor R:R (< 1.5:1)

            Return ONLY valid JSON. Never return invalid trades.
            """,
            ),
            (
                "system",
                """
                Market data:
                Alpaca is the brokerage data, Yahoo provides recent historicals.
                You are to analyse and provide technical justifications based on this data.
                Use this market data to find exact entry price, stop loss and take profit levels.
                {market_summary}
                """
                
            ),
            (
                "human",
                """
            NEWS SIGNAL:
            Sentiment: {sentiment} (score: {score})
            Event Type: {event_type}

            ANALYSIS REQUIRED:
            1. News impact assessment
            2. Technical setup (support/resistance, RSI, momentum)
            3. Volatility regime (swing viable?)
            4. Entry/SL/TP calculation (ATR-based)
            5. Position sizing (keep it to 10)
            6. Clear thesis (why this swing works)

            entry price should be within current stock price and place strategically based on market data.
            double check stop_loss and take_profit price, it should be relative to entry price.
            if action is sell, stop_loss should be higher than entry price, take_profit should be lower than entry price;
            if action is buy, stop_loss should be lower than entry price, take_profit should be higher than entry price;
            Do not add comments to the JSON output.
            do not use special characters in thesis content.
            Return in this exact JSON format:
            {{
            "action": "BUY" | "SELL" | "HOLD",
            "confidence": 0.0-1.0,
            "entry_price": float,
            "stop_loss": float,
            "take_profit": float,
            "qty": float,
            "risk_reward": "X:1",
            "thesis": "Detailed reasoning with news + technical justification (also provide figures from market data to support your entry and exit leveels)"
            "current_stock_price": float, # the current stock price from market data
            }}
            
            
            if you think there should not be any trade, return action as HOLD with qty 0.
            """,
            ),
        ]
    )

    # 2. Prepare enriched input for LLM
    input_vars = {
        "ticker": state["ticker"],
        "sentiment": state["signal"].get("sentiment", "neutral"),
        "score": state["signal"].get("score", 0.0),
        "event_type": state["signal"].get("event_type", "general"),
        "market_summary": market_summary
    }

    # 3. Invoke LLM
    chain = prompt | llm
    response = await chain.ainvoke(input_vars)
    
    decision = parse_llm_json(response.content)
    if decision.get("action") not in ["BUY", "SELL", "HOLD"]:
        decision["action"] = "HOLD"
        
    return {
        "order_details": {
            **decision,
            "ticker": state["ticker"],
            "has_trade_opportunity": decision.get("action") in ["BUY", "SELL"]
        },
    }

# Helper function to parse LLM JSON responses robustly
def parse_llm_json(response_content: str) -> dict:
    content = response_content.strip()
    print("Raw LLM:", content)
    
    # Step 1: Extract JSON (handles ```json, ```, raw, or nested)
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL | re.IGNORECASE)
    if json_match:
        raw_json = json_match.group(1)
    else:
        # Largest valid JSON block fallback
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content)
        raw_json = json_match.group(0) if json_match else content.strip()
    
    # Step 2: Strip comments & normalize
    raw_json = re.sub(r'//.*?(?=\n|$)', '', raw_json, flags=re.MULTILINE)     # // comments
    raw_json = re.sub(r'/\*.*?\*/', '', raw_json, flags=re.DOTALL)           # /* */ comments
    raw_json = raw_json.replace("'", '"').replace('True', 'true').replace('False', 'false')  # Fix quotes/booleans
    
    try:
        decision = json.loads(raw_json)
        print("✅ Parsed:", decision)
        return decision
    except json.JSONDecodeError as e:
        print(f"❌ Parse failed: {e} | Raw: {raw_json[:200]}...")
        return fallback_decision()

def fallback_decision() -> dict:
    return {
        "action": "HOLD",
        "confidence": 0.0,
        "entry_price": 0.0,
        "stop_loss": 0.0,
        "take_profit": 0.0,
        "qty": 0.0,
        "risk_reward": "0:1",
        "thesis": "JSON parsing error - no trade",
    }