[📡 Fetch Signal] Fetching signal data for signal_id: 69a6e16ffabcdb2cb6bc2c09...
http://localhost:8000/api/v1/trading/decisions/signals/69a6e16ffabcdb2cb6bc2c09
   [✅ Fetch Signal] Successfully fetched signal data for signal_id: 69a6e16ffabcdb2cb6bc2c09.
   [📊 Market Data] Fetching data for GRND...

LATEST MARKET DATA FROM YAHOO FINANCE FOR ANALYSIS:
TECHNICAL INDICATORS (61 bars, 2025-12-03→2026-03-03):
- Price: $11.37
- SMA20: $10.77 (above)
- SMA50: $11.97
- RSI(14): 58.6 (neutral)
- ATR(14): $0.57
- Support: $9.73
- Resistance: $12.28


LIVE QUOTE FROM BROKER (GRND, 2026-03-03T19:27:40.221921+00:00):
- Current Price: $11.38
- Bid: $9.77 x 100
- Ask: $11.38 x 100
- Spread: $1.610 (14.1%)


Use this fresh market data to inform your trading decision.
   [✅ Market Data Fetched] Alpaca and Yahoo data added to state.
   [🧠 Swing Trading Brain] Analyzing GRND...
   [✅ LLM Response Parsed] Success on attempt 1
   [🧠 Brain Decision] Trade opportunity identified! Action: BUY, Entry: $11.38, SL: $10.71, TP: $13.17
   [✅ Brain Output] Formatted Trade Decision:
------------------------------------------------------------
🎯 TRADE DECISION
Action: BUY (90.0%)
Entry: $11.38 | SL: $10.71 | TP: $13.17
Qty: 2.0 | R:R 1.7:1
Price: $11.38

High credibility news confirms 28% revenue growth to $440M, 44% EBITDA margins, $103M net income, and $400M buyback (18% of $2.17B mcap) through 2029, with 2026 guidance >$528M revenue and >$217M EBITDA per official disclosures; Goldman Sachs maintains BUY with $17 PT (49% upside from $11.38); DCF models show 66% undervaluation to $34. Technicals: price $11.38 above SMA20 $10.77 but below SMA50 $11.97, RSI 58.6 neutral (room to run), support $9.73/resistance $12.28; ATR $0.57 confirms volatility for swings. Entry at ask $11.38; SL at entry - ATR $10.81 rounded to $10.71 (near bid support $9.77); TP at entry + 3x risk $13.17 (past resistance toward $17 PT). R:R 1.7:1 meets criteria.
------------------------------------------------------------

   [✅ Trade Opportunity] Yes
   [🛡️ Risk Layer] Evaluating trade risk...
   [💰 Buying Power] 32305.96
   [🛡️ Risk Layer] Risk score 1.05/1.50
[🛡️ RISK LAYER RESULT] {'status': 'no_conflict', 'symbol': 'GRND', 'message': 'No conflicts found - ready to trade'}

   [🛡️ Risk Layer] No conflicts detected for GRND.
   [🛡️ Risk Layer] Conflict Resolution status: No Conflict Detected
   [🛡️ Risk Layer] Should Execute?  True
   [🚀 Execute Trade] Starting trade execution node...
   [📈 Market Access] Executing 
🎯 TRADE DECISION
Action: BUY (90.0%)
Entry: $11.38 | SL: $10.81 | TP: $12.28
Qty: 142.0 | R:R 1.7:1
Price: $11.38

High credibility news confirms 28% revenue growth to $440M, 44% EBITDA margins, $103M net income, and $400M buyback (18% of $2.17B mcap) through 2029, with 2026 guidance >$528M revenue and >$217M EBITDA per official disclosures; Goldman Sachs maintains BUY with $17 PT (49% upside from $11.38); DCF models show 66% undervaluation to $34. Technicals: price $11.38 above SMA20 $10.77 but below SMA50 $11.97, RSI 58.6 neutral (room to run), support $9.73/resistance $12.28; ATR $0.57 confirms volatility for swings. Entry at ask $11.38; SL at entry - ATR $10.81 rounded to $10.71 (near bid support $9.77); TP at entry + 3x risk $13.17 (past resistance toward $17 PT). R:R 1.7:1 meets criteria.
   [📤 API] POST http://localhost:8000/api/v1/trading/orders/bracket
   [📤 Payload] {'symbol': 'GRND', 'side': 'buy', 'qty': 142.0, 'entry_type': 'limit', 'take_profit_price': 12.28, 'stop_loss_price': 10.81, 'time_in_force': 'gtc', 'entry_price': 11.38}
   [✅ SUCCESS] Order ID: e8592d5d-5bb9-4c53-a835-bfd297697bea
   [✅ Execution Result] Order ID set in state: e8592d5d-5bb9-4c53-a835-bfd297697bea
   [📝 Trade Logging] Starting trade logging node...
   [📝 Trade Logging] Prepared DB Payload: e8592d5d-5bb9-4c53-a835-bfd297697bea
   [📝 Trade Logging] Sending to DB: ['e8592d5d-5bb9-4c53-a835-bfd297697bea']
   [✅ Trade Logging] DB Response: {'success': 1, 'failed': 0}