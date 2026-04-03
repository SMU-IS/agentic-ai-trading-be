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

    ### DEBUG STAGE
    # print(f"   [🧠 Swing Trading Brain] Analyzing {signal_data.ticker}...")
    # # DEBUG - SKIP LLM CALLS
    # decision = TradingDecision(
    #                     action=TradeAction.SELL,
    #                     confidence=0.85,
    #                     entry_price=22.02,
    #                     stop_loss=23,
    #                     take_profit=20.5,
    #                     qty=4.5,
    #                     risk_reward=1.6,
    #                     thesis="Strong catalyst from GLP-1 deal with Novo Nordisk and legal resolution drove 50% surge in early March 2026 with 2.5x volume and breakout above $26.03 resistance[1], but recent price action shows sharp reversal and overreaction: Mar 11 high $27.54, Mar 12 close $23.84 (-7.88%), Mar 18 close $23.15 (-7.33%) on elevated volume 34M+ shares[1]. Current $22.02 reflects STRONG_BEARISH candle (8.1% body drop to $21.70 low), 0.6x average volume signaling exhaustion, RSI 50 neutral, price 63% into BB upper $28.454 but below SMA50 $23.150 and key resistance $27.540[market data]. Euphoric spike into resistance post-news creates fade opportunity as momentum fades (MACD histogram +0.7585 but price below SMA20 $19.829? wait data shows recent highs above), support $21.700 and $13.740 for downside. Entry at current $22.02, SL above SMA50 $23.150 at $23.80 (1.8x ATR $0.010-based ~$1.78 risk), TP at 3D range low $20.50 for asymmetric reward into support.",
    #                     current_stock_price=22.02,
    #                     ticker=signal_data.ticker
    #                 )
    # state["has_trade_opportunity"] = decision.action in [TradeAction.BUY, TradeAction.SELL]
    # print(f"   [✅ Trade Opportunity] {'Yes' if state['has_trade_opportunity'] else 'No'}")
    # state["order_details"] = decision

    # return state
    ### END OF DEBUG

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
            You trade reactions not stories.


            STEP 1 - CLASSIFY THE CATALYST:
            A catalyst is STRONG if it is: earnings surprise, FDA decision, M+A announcement, regulatory action, major legal ruling, or institutional research from a top-tier firm with documented track record.
            A catalyst is WEAK if it is: social media rumor, speculative short-seller opinion, analyst price target change, sentiment piece, or unverified report.
            Label it clearly before proceeding.


            STEP 2 - CLASSIFY TODAY'S PRICE ACTION:
            Check open vs close vs high vs low vs 3-day range.
            If close is near high and the range is large, price RECOVERED (flush-and-recover).
            If close is near low and the range is large, price SOLD OFF (spike-and-dump).
            A flush-and-recover means the news shock was already absorbed intraday. The market rejected the move. Do not fade a move that already reversed.
            A spike-and-dump means sellers took control. Continuation or fade requires further confirmation.


            STEP 3 - VOLUME GATE:
            vol_ratio is volume today vs average volume.
            vol_ratio below 0.6: FAIL. Low participation. No institutional conviction. Any signal is LOW QUALITY. Bias toward HOLD.
            vol_ratio 0.6 to 1.2: PASS. Average participation. Signal is valid. This is not a failure — count it as a confirmed alignment factor.
            vol_ratio above 1.2: PASS (elevated). High quality signal. Institutional involvement likely. Counts as a strong alignment factor.
            Do not assign continuation or fade bias without passing this gate.
            Do not treat vol_ratio 0.6-1.2 as insufficient — it is a passing grade, not a borderline failure.


            STEP 4 - APPLY INTERPRETATION RULES (only after Steps 1-3):
            Strong catalyst + vol_ratio above 1.2 + breakout candle = continuation bias
            Weak catalyst + vol_ratio above 1.2 + parabolic overextension above BB upper or resistance = fade bias
            Flush-and-recover candle + price near support + vol_ratio above 0.6 = mean reversion BUY
            Spike-and-dump candle + price near resistance + vol_ratio above 0.6 = mean reversion SHORT
            Any conflicting signals across Steps 1-3 = HOLD. Do not force a trade.
            RSI below 70 and price not at resistance = no overbought confirmation, do not short on thesis alone.
            RSI above 90 is an exceptional exhaustion signal. RSI above 90 + price at or near resistance + candle rejection = three alignment factors met on their own. Do not dismiss RSI above 90 as just one vote among equals.
            MACD bearish but candle bullish = mixed signal = HOLD unless vol_ratio above 1.2 confirms one side.
            MACD bullish but candle bearish at resistance with RSI above 90 = RSI and price structure override MACD. Count candle and RSI as aligned, not MACD.


            STEP 5 - CONFLICT CHECK (run before finalizing):
            If the proposed action is SELL but today's candle is bullish and closed near its high, that is a direct contradiction. Return HOLD.
            If the proposed action is BUY but today's candle is bearish and closed near its low, that is a direct contradiction. Return HOLD.
            Count each of the following as one alignment factor. You need at least 3 to proceed:
            - Catalyst quality: a STRONG catalyst supports continuation. A WEAK catalyst on an overbought or overextended stock supports a fade. Either way, if the catalyst direction is consistent with your proposed action, count it.
            - Volume confirmation: vol_ratio above 0.6 is a confirmed pass. Count it.
            - Candle direction: if the candle type (bullish, bearish, neutral) is consistent with the proposed action, count it. A moderate bearish candle supports SELL. A moderate bullish candle supports BUY. A neutral candle counts as 0.
            - Momentum (MACD): MACD histogram direction aligned with proposed action counts. Opposing MACD does not count but does not automatically block the trade unless it is the only signal.
            - RSI extreme: RSI above 75 for a SELL or below 30 for a BUY counts. RSI above 90 or below 15 counts double.
            - Proximity to key level: price within 2 percent of resistance (for SELL) or support (for BUY) counts.
            Tally the count explicitly in your thesis. If fewer than 3 align, return HOLD.


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
                Ignore the upstream stop_loss_pct and target_pct percentages when setting price levels. Build entry, stop loss, and take profit purely from current market price, ATR, and key levels in the data below.
                {market_summary}
                """,
            ),
            (
                "human",
                """
            Here are the inputs for {ticker}:
            News Summary: {romour_summary}
            Catalyst Credibility: {credibility} ({credibility_reason})
            Initial Signal Direction: {trade_signal}
            Signal Confidence: {confidence}
            Signal Rationale: {trade_rationale}

            NOTE: The initial signal is a starting point only. It may be stale or anchored to wrong price levels.
            Your job is to validate or override it using the market data and the rules above.
            Do not inherit the signal's entry or exit levels. Derive your own from current price and ATR.


            ANALYSIS REQUIRED:
            1. Catalyst classification (STRONG or WEAK, and why)
            2. Price action classification (flush-and-recover, spike-and-dump, or neutral)
            3. Volume gate result (vol_ratio value and quality assessment)
            4. Conflict check result (how many of the 5 alignment factors are confirmed)
            5. Entry/SL/TP levels derived from current price and ATR14
            6. Position size (max qty 10)
            7. Thesis explaining why the trade is valid or why it is a HOLD

            Entry must be within 1 ATR of the current stock price.
            For SELL: stop_loss must be above entry, take_profit must be below entry.
            For BUY: stop_loss must be below entry, take_profit must be above entry.
            Minimum risk/reward ratio is 2:1. If you cannot achieve 2:1 cleanly, return HOLD.
            Do not add comments to the JSON output.
            Do not use special characters in thesis content.

            Return in this exact JSON format:
            {{
            "action": "BUY" | "SELL" | "HOLD",
            "confidence": 0.0-1.0,
            "entry_price": float,
            "stop_loss": float,
            "take_profit": float,
            "qty": float,
            "risk_reward": "X:1",
            "thesis": "Catalyst type, price action type, volume gate result, alignment count, and specific price levels from market data that justify the trade or the HOLD decision",
            "current_stock_price": float
            }}

            If there is no valid trade, return action as HOLD with qty 0.
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
