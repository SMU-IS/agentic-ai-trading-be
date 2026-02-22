import json
import re

from langchain_core.prompts import ChatPromptTemplate
from app.agents.state import AgentState, TradingDecision, TradeAction


async def node_decide_trade(llm, state: AgentState) -> AgentState:
    """
    Brain: Uses LLM for short-term swing trades driven by news volatility.
    Goal: Capture 2-5 day swings against short-term news-driven volatility.
    """

    signal_data = state["signal_data"]
    market_summary = state["market_data"].to_prompt() if state.get("market_data") else "No market data available."
    # 2. Prepare enriched input for LLM
    input_vars = {
        "ticker": signal_data.ticker,
        "romour_summary": signal_data.rumor_summary,
        "credibility": signal_data.credibility,
        "credibility_reason": signal_data.credibility_reason,
        "trade_signal": signal_data.trade_signal,
        "confidence": signal_data.confidence,
        "trade_rationale": signal_data.trade_rationale,
        "position_size_pct": signal_data.position_size_pct,
        "stop_loss_pct": signal_data.stop_loss_pct,
        "target_pct": signal_data.target_pct,

        "market_summary": market_summary,

    }

    print(f"   [🧠 Swing Trading Brain] Analyzing {signal_data.ticker}...")
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
                """,
            ),
            (
                "human",
                """
            Here are some insights about the trade signal and market context for {ticker}:
            Rumor: {romour_summary}
            Credibility: {credibility} ({credibility_reason})
            Trade Signal: {trade_signal}
            Confidence: {confidence}
            Trade Rationale: {trade_rationale}
            Position Size: {position_size_pct}%
            Stop Loss: {stop_loss_pct}%
            Target: {target_pct}%


            ANALYSIS REQUIRED:
            1. News impact assessment
            2. Technical setup (support/resistance, RSI, momentum)
            3. Volatility regime (swing viable?)
            4. Entry/SL/TP calculation (ATR-based)
            5. Position sizing (keep it to 10)
            6. Clear thesis (why this swing works)

            entry price should be within current stock price and place strategically based on market data. entry price should not be too far from current stock price.
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

            DEBUG FEATURE: If you are unsure about the trade, return a HOLD with a detailed thesis explaining why you are uncertain. This will help improve the model over time.
            TESTING NOTE: For testing purpose, you can return a BUY with entry price just slightly above current stock price, and stop loss just below current stock price, to simulate a valid swing trade.
            
            CURRENT MODE: TESTING
            """,
            ),
        ]
    )

    # 3. Invoke LLM
    chain = prompt | llm
    try:
        response = await chain.ainvoke(input_vars)
        decision = parse_llm_json(response.content)
        print("   [✅ LLM Response Parsed] successfully parsed trade decision.")
        ### Ensure ticker is included in decision for downstream nodes
        decision.ticker = signal_data.ticker 

        ### [DEBUG] For testing, hardcoding decision
        # decision = TradingDecision(
        #     action=TradeAction.BUY, 
        #     confidence=0.3, 
        #     entry_price=202.93, 
        #     stop_loss=195.54, 
        #     take_profit=210.91, 
        #     qty=0, 
        #     risk_reward='1.2:1', 
        #     thesis="DEBUG ON; Testing mode enabled.", 
        #     current_stock_price=202.69, 
        #     ticker='AMZN')
    except Exception as e:
        print(f"   [❌ LLM Error] {e}")
        decision = TradingDecision(
            action=TradeAction.HOLD,
            confidence=0.0,
            entry_price=0.0,
            stop_loss=0.0,
            take_profit=0.0,
            qty=0.0,
            risk_reward="0:1",
            thesis="LLM error - no trade",
            current_stock_price=0.0,
            ticker=signal_data.ticker
        )

    if decision.action == TradeAction.HOLD:
        print("   [🧠 Brain Decision] No trade opportunity identified. Action: HOLD")
    else:
        print(f"   [🧠 Brain Decision] Trade opportunity identified! Action: {decision.action}, Entry: ${decision.entry_price:.2f}, SL: ${decision.stop_loss:.2f}, TP: ${decision.take_profit:.2f}")
    
    print("   [✅ Brain Output] Formatted Trade Decision:")
    print("-" * 60)
    print(decision.to_prompt())
    print("-" * 60)
    print()

    state["has_trade_opportunity"] = decision.action in [TradeAction.BUY, TradeAction.SELL]
    print(f"   [✅ Trade Opportunity] {'Yes' if state['has_trade_opportunity'] else 'No'}")
    state["order_details"] = decision
    return state


# Helper function to parse LLM JSON responses robustly
def parse_llm_json(response_content: str) -> dict:
    content = response_content.strip()

    # Step 1: Extract JSON (handles ```json, ```, raw, or nested)
    json_match = re.search(
        r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL | re.IGNORECASE
    )
    if json_match:
        raw_json = json_match.group(1)
    else:
        # Largest valid JSON block fallback
        json_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", content)
        raw_json = json_match.group(0) if json_match else content.strip()

    # Step 2: Strip comments & normalize
    raw_json = re.sub(r"//.*?(?=\n|$)", "", raw_json, flags=re.MULTILINE)  # // comments
    raw_json = re.sub(r"/\*.*?\*/", "", raw_json, flags=re.DOTALL)  # /* */ comments
    raw_json = (
        raw_json.replace("'", '"').replace("True", "true").replace("False", "false")
    )  # Fix quotes/booleans

    try:
        decision = json.loads(raw_json)
        decision = TradingDecision.from_dict(decision)
        return decision
    except json.JSONDecodeError as e:
        print(f"❌ Parse failed: {e} | Raw: {raw_json}...")
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
