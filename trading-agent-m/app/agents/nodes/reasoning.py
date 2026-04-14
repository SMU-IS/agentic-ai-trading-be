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

    if state.get("market_data"):
        md = state["market_data"]
        y  = md.yahoo
        a  = md.alpaca

        def _f(v, fmt=""):
            if v is None: return "N/A"
            try: return f"{v:{fmt}}"
            except: return str(v)

        rsi_label = "OVERSOLD" if y.rsi and y.rsi < 30 else "OVERBOUGHT" if y.rsi and y.rsi > 75 else "NEUTRAL"
        spread_pct = (a.spread / a.latest_trade.price * 100) if a.latest_trade.price else 0.0

        market_summary = f"""PRICE ACTION SUMMARY:
- Current Price: ${_f(a.latest_trade.price, '.3f')} (live broker quote)
- Candle: {y.candle_type.upper()} (body {_f(y.body_size, '.1f')}%, {_f(y.body_pct, '.0%')} of range)
- Range: ${_f(y.low, '.3f')} - ${_f(y.high, '.3f')} | ATR14: ${_f(y.atr14, '.3f')}
- 3D Range: ${_f(y.low_3d, '.3f')} - ${_f(y.high_3d, '.3f')}
- Penny Stock: {'YES' if y.is_penny else 'NO'}

TECHNICAL INDICATORS:
- RSI: {_f(y.rsi, '.1f')} ({rsi_label})
- SMA20: ${_f(y.sma20, '.3f')} | SMA50: ${_f(y.sma50, '.3f')} | SMA200: ${_f(y.sma200, '.3f')}
- MACD: {_f(y.macd, '.4f')} | Signal: {_f(y.macd_signal, '.4f')} | Histogram: {_f(y.macd_histogram, '+.4f')}
- BB Lower: ${_f(y.bb_lower, '.3f')} | BB Upper: ${_f(y.bb_upper, '.3f')} | BB Middle: ${_f(y.bb_middle, '.3f')} | Position: {_f(y.bb_position, '.0%')}

MARKET STRUCTURE:
- Support: ${_f(y.support, '.3f')} | Resistance: ${_f(y.resistance, '.3f')}
- Data Period: {y.period_summary}

LIVE BROKER QUOTE ({a.latest_trade.symbol}, {a.latest_trade.timestamp}):
- Bid: ${_f(a.latest_quote.bid_price, '.2f')} x {a.latest_quote.bid_size} | Ask: ${_f(a.latest_quote.ask_price, '.2f')} x {a.latest_quote.ask_size}
- Spread: ${_f(a.spread, '.3f')} ({spread_pct:.2f}%)"""
    else:
        market_summary = "No market data available."

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
        "market_summary": market_summary
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
            Use the Candle type, Range (Low-High), and 3D Range from market data.
            If the candle closed near its high and the range is large relative to ATR14, price RECOVERED (flush-and-recover).
            If the candle closed near its low and the range is large relative to ATR14, price SOLD OFF (spike-and-dump).
            A flush-and-recover means the news shock was absorbed intraday — the market rejected the move. Do not fade a move that already reversed.
            A spike-and-dump means sellers took control. Fade requires further confirmation from RSI and key levels.
            If the live Current Price (from broker) is more than 1% above the OHLCV High shown in Range, the stock has gapped above yesterday's candle. Treat this as a breakout in the direction of the gap. Do not classify it as neutral.


            STEP 3 - APPLY INTERPRETATION RULES (only after Steps 1-2):
            Strong catalyst + breakout candle = continuation bias
            Weak catalyst + parabolic overextension above BB upper or resistance = fade bias
            Flush-and-recover candle + price near support = mean reversion BUY
            Spike-and-dump candle + price near resistance = mean reversion SHORT
            Any conflicting signals across Steps 1-2 = HOLD. Do not force a trade.
            RSI below 70 and price not at resistance = no overbought confirmation, do not short on thesis alone.
            RSI above 90 is an exceptional exhaustion signal. RSI above 90 + price at or near resistance + candle rejection = three alignment factors met on their own. Do not dismiss RSI above 90 as just one vote among equals.
            MACD bearish but candle bullish = mixed signal = HOLD.
            MACD bullish but candle bearish at resistance with RSI above 90 = RSI and price structure override MACD. Count candle and RSI as aligned, not MACD.


            STEP 4 - CONFLICT CHECK (run before finalizing):
            Only return HOLD for a direct contradiction: SELL with a bullish candle closed near its high, or BUY with a bearish candle closed near its low.
            Count each of the following as one alignment factor:
            - Catalyst quality: a STRONG catalyst supports continuation. A WEAK catalyst on an overbought or overextended stock supports a fade. Count if direction matches proposed action.
            - Candle direction: use the Candle field. Bullish candle supports BUY. Bearish candle supports SELL. Neutral = 0.
            - Momentum (MACD): use the Histogram value. Positive histogram supports BUY. Negative supports SELL. Opposing does not block unless it is the only signal.
            - RSI extreme: use the RSI value. Above 75 for SELL counts. Below 30 for BUY counts. Above 90 or below 15 counts double. The label (OVERBOUGHT/OVERSOLD/NEUTRAL) in the market data is for reference — always use the actual RSI number.
            - Proximity to key level: use Support and Resistance from MARKET STRUCTURE. Current Price within 2% of Resistance for SELL counts. Within 2% of Support for BUY counts.
            Tally the count in your thesis.
            A STRONG catalyst alone (count = 1) is sufficient to proceed if there are no direct contradictions.
            A WEAK catalyst requires at least 2 additional confirming factors (total >= 3) before proceeding.
            Do not block a speculative trade on a STRONG catalyst simply because technicals are neutral.


            Return ONLY valid JSON. Never return invalid trades.
            """,
            ),
            (
                "human",
                """MARKET DATA FOR {ticker}:
All fields below are present. Do not state that any field is unavailable or missing.

Field reference:
- Current Price: live broker quote (use this as current_stock_price)
- Candle: yesterday's OHLCV candle type, body%, body-to-range ratio
- Range: yesterday's Low - High, ATR14 (14-day average true range in dollars)
- RSI: momentum oscillator 0-100. OVERBOUGHT label = above 75. OVERSOLD label = below 30.
- SMA20 / SMA50 / SMA200: simple moving averages — use for trend direction and TP targets
- MACD / Signal / Histogram: histogram positive = bullish momentum, negative = bearish
- BB Lower / Upper / Position%: Bollinger Bands. Position 0% = at lower band, 100% = at upper band
- Support / Resistance: structural levels from 30-day price history — use as SL/TP anchors
- 3D Range: highest high and lowest low over last 3 days
- Bid / Ask / Spread: live broker quote — confirms current tradeable price

{market_summary}

---

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
            3. Conflict check result (how many alignment factors are confirmed)
            4. Entry type determination (at-market or anticipatory — see rules below)
            5. Entry/SL/TP levels built from key levels and ATR14
            6. Position size (max qty 10)
            7. Thesis explaining why the trade is valid or why it is a HOLD


            ENTRY PRICING RULES:
            Follow these steps in order. Do not skip steps or estimate — calculate each value explicitly.

            STEP A — IDENTIFY KEY LEVELS:
            From MARKET STRUCTURE: Support, Resistance.
            From TECHNICAL INDICATORS: BB Lower, BB Upper, BB Middle, SMA20.
            ATR14 comes from the Range line. Use the exact dollar value shown.

            STEP B — CHOOSE ENTRY MODE:
            AT-MARKET: use when Current Price is within 0.5 x ATR14 of the key level (Support for BUY, Resistance for SELL). Entry = Current Price.
            ANTICIPATORY: use when RSI is below 20 (BUY) or above 80 (SELL) AND Current Price has not yet reached the structural level. Entry = the key level itself. Must be within 2 x ATR14 of Current Price, otherwise use AT-MARKET.

            STEP C — SET STOP LOSS:
            For BUY: SL = invalidation level (lower of Support or BB Lower) minus 0.25 x ATR14.
            For SELL: SL = invalidation level (higher of Resistance or BB Upper) plus 0.25 x ATR14.
            SL sits beyond the structural level so normal volatility does not trigger it.

            STEP D — SET TAKE PROFIT:
            For BUY: TP = nearest target above entry (Resistance, SMA20, or BB Middle) minus 0.15 x ATR14.
            For SELL: TP = nearest target below entry (Support, SMA20, or BB Middle) plus 0.15 x ATR14.
            TP stops short of the target so the order fills before a natural reversal at that level.

            STEP E — VERIFY RISK/REWARD:
            Calculate: risk = abs(entry - stop_loss), reward = abs(take_profit - entry), RR = reward / risk.
            Show this calculation explicitly in the thesis: "risk=$X, reward=$X, RR=X:1".
            If RR is below 2.0, the trade does not have a valid setup — return HOLD.
            Do not round or inflate the RR figure. Use the exact calculated value.

            UNIVERSAL RULES:
            For SELL: stop_loss must be above entry, take_profit must be below entry.
            For BUY: stop_loss must be below entry, take_profit must be above entry.
            State clearly in the thesis the entry mode (at-market or anticipatory) and the key level targeted.
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
            "thesis": "Catalyst type, price action type, alignment count, entry mode (at-market or anticipatory), key level targeted, and specific price levels that justify the trade or the HOLD decision",
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

    has_trade = decision.action in [TradeAction.BUY, TradeAction.SELL]
    print(f"   [✅ Trade Opportunity] {'Yes' if has_trade else 'No'}")
    return {
        "has_trade_opportunity": has_trade,
        "order_details": decision,
    }


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
    raw_json = raw_json.replace("True", "true").replace("False", "false")  # Fix booleans

    try:
        decision = json.loads(raw_json)
        decision = TradingDecision.from_dict(decision)
        return decision
    except json.JSONDecodeError as e:
        print(f"❌ Parse failed: {e} | Raw: {raw_json}...")
        raise


def fallback_decision() -> TradingDecision:
    return TradingDecision(
        action=TradeAction.HOLD,
        confidence=0.0,
        entry_price=0.0,
        stop_loss=0.0,
        take_profit=0.0,
        qty=0.0,
        risk_reward="0:1",
        thesis="JSON parsing error - no trade",
        current_stock_price=0.0,
    )
