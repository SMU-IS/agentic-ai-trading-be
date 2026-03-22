import json
import re
import asyncio
from langchain_core.prompts import ChatPromptTemplate
from app.agents.state import AgentState, TradingDecision, TradeAction


async def node_decide_trade(llm, state: AgentState) -> AgentState:
    """
    Brain: Uses LLM for short-term swing trades driven by news volatility.
    Goal: Capture 2-5 day swings against short-term news-driven volatility.
    """
    signal_data = state["signal_data"]
    print(f"   [🧠 Swing Trading Brain] Analyzing {signal_data.ticker}...")
    ## DEBUG - SKIP LLM CALLS
    decision = TradingDecision(
                        action=TradeAction.SELL,
                        confidence=0.85,
                        entry_price=22.02,
                        stop_loss=23,
                        take_profit=20.5,
                        qty=4.5,
                        risk_reward=1.6,
                        thesis="Strong catalyst from GLP-1 deal with Novo Nordisk and legal resolution drove 50% surge in early March 2026 with 2.5x volume and breakout above $26.03 resistance[1], but recent price action shows sharp reversal and overreaction: Mar 11 high $27.54, Mar 12 close $23.84 (-7.88%), Mar 18 close $23.15 (-7.33%) on elevated volume 34M+ shares[1]. Current $22.02 reflects STRONG_BEARISH candle (8.1% body drop to $21.70 low), 0.6x average volume signaling exhaustion, RSI 50 neutral, price 63% into BB upper $28.454 but below SMA50 $23.150 and key resistance $27.540[market data]. Euphoric spike into resistance post-news creates fade opportunity as momentum fades (MACD histogram +0.7585 but price below SMA20 $19.829? wait data shows recent highs above), support $21.700 and $13.740 for downside. Entry at current $22.02, SL above SMA50 $23.150 at $23.80 (1.8x ATR $0.010-based ~$1.78 risk), TP at 3D range low $20.50 for asymmetric reward into support.",
                        current_stock_price=22.02,
                        ticker=signal_data.ticker
                    )
    state["has_trade_opportunity"] = decision.action in [TradeAction.BUY, TradeAction.SELL]
    print(f"   [✅ Trade Opportunity] {'Yes' if state['has_trade_opportunity'] else 'No'}")
    state["order_details"] = decision

    return state

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
            You do NOT invest long term.  
            You do NOT speculate without catalysts.  
            You trade reactions — not stories.

            1. Detect news-driven sentiment shocks.
            2. Evaluate whether the market reaction is:
                - Rational continuation  
                - Emotional overreaction (bullish or bearish)
            3. Trade against extreme sentiment when risk/reward is asymmetric.
            4. If reaction is proportional and no edge exists return NO_TRADE.

            Evaluate:
            - Recent price movement (gap up/down, range expansion)
            - Relative strength vs broader market
            - Volume spike (institutional participation)
            - Options flow extremes (if available)
            - Proximity to support/resistance
            - Overextension from moving averages (short-term exhaustion)
            
            Interpretation Rules:
            - Strong catalyst + strong volume breakout → continuation bias
            - Weak catalyst + parabolic move → fade bias
            - Panic flush into support → mean reversion BUY
            - Euphoric spike into resistance → mean reversion SHORT
            - No technical confirmation → `NO_TRADE`
            
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
            """,
            ),
        ]
    )

    # 3. Invoke LLM
    chain = prompt | llm
    MAX_RETRIES = 2  # number of retries after first attempt

    decision = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = await chain.ainvoke(input_vars)
            decision = parse_llm_json(response.content)

            print(f"   [✅ LLM Response Parsed] Success on attempt {attempt + 1}")

            # Ensure ticker is included in decision for downstream nodes
            decision.ticker = signal_data.ticker
            break  # exit loop if successful

        except Exception as e:
            print(f"   [⚠️ LLM Error] Attempt {attempt + 1} failed: {e}")

            if attempt < MAX_RETRIES:
                await asyncio.sleep(1.5 * (attempt + 1))  # simple backoff
            else:
                print("   [❌ LLM Failed After Retries] Defaulting to HOLD")

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
