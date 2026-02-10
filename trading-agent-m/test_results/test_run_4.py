# === Testing TradingWorkflow with Ollama ===

# 🧪 Test Case 1: AAPL (bearish)
# ------------------------------------------------------------
#    [🔍 Qdrant] Searching for historical context on AAPL...
#    [⚡ Qdrant] Connection initialized to http://localhost:8333
#    [🔍 Qdrant] Generated dummy query vector.
#    [✅ Qdrant] Retrieved 5 results for AAPL.
#    [📊 Market Data] Fetching data for AAPL...
#    [📈 Yahoo Market Data] {'indicators': {'price': 274.57000732421875, 'atr14': 6.698574611118862, 'sma20': 258.3209991455078, 'sma50': 268.5313989257813, 'support': 243.4199981689453, 'resistance': 278.80999755859375}, 'summary': '63 bars, 2025-11-04→2026-02-04'}
#    [📈 Alpaca Market Data] {'latest_quote': {'symbol': 'AAPL', 'bid_price': 274.13, 'bid_size': 100, 'ask_price': 274.64, 'ask_size': 100, 'timestamp': '2026-02-04T16:55:20.206347+00:00', 'conditions': ['R'], 'tape': 'C'}, 'latest_trade': {'symbol': 'AAPL', 'price': 274.63, 'size': 200, 'exchange': 'V', 'conditions': ['@'], 'timestamp': '2026-02-04T16:55:20.935757+00:00', 'id': '13501', 'tape': 'C'}, 'spread': 0.5099999999999909}
#    [🧠 Swing Trading Brain] Analyzing AAPL...
# Raw LLM: {
#     "action": "SELL",
#     "confidence": 0.8,
#     "entry_price": 274.13,
#     "stop_loss": 276.5,
#     "take_profit": 272.2,
#     "qty": 10,
#     "risk_reward": "1:1.4",
#     "thesis": "The bearish sentiment score of -0.75 indicates a strong negative reaction to the earnings miss, creating a swing opportunity. The stock is near resistance (278.81) and overbought (RSI > 70), confirming the sell signal. Volatility is high (ATR > 20-day average), making this trade viable. Entry at 274.13, stop-loss at 276.5 (1% above entry), take-profit at 272.2 (1% below entry).",
#     "current_stock_price": 274.57
# }
# ✅ Parsed: {'action': 'SELL', 'confidence': 0.8, 'entry_price': 274.13, 'stop_loss': 276.5, 'take_profit': 272.2, 'qty': 10, 'risk_reward': '1:1.4', 'thesis': 'The bearish sentiment score of -0.75 indicates a strong negative reaction to the earnings miss, creating a swing opportunity. The stock is near resistance (278.81) and overbought (RSI > 70), confirming the sell signal. Volatility is high (ATR > 20-day average), making this trade viable. Entry at 274.13, stop-loss at 276.5 (1% above entry), take-profit at 272.2 (1% below entry).', 'current_stock_price': 274.57}
#    [🛡️ Risk Layer] Evaluating trade risk...
#    [💰 Buying Power] 74271.8
# {'risk_status': 'APPROVED', 'risk_score': 1.25, 'adjusted_trade': {'action': 'SELL', 'confidence': 0.8, 'entry_price': 274.13, 'stop_loss': 278.80999755859375, 'take_profit': 261.1728507777623, 'qty': 10, 'risk_reward': '1:1.4', 'thesis': 'The bearish sentiment score of -0.75 indicates a strong negative reaction to the earnings miss, creating a swing opportunity. The stock is near resistance (278.81) and overbought (RSI > 70), confirming the sell signal. Volatility is high (ATR > 20-day average), making this trade viable. Entry at 274.13, stop-loss at 276.5 (1% above entry), take-profit at 272.2 (1% below entry).', 'current_stock_price': 274.57, 'ticker': 'AAPL', 'has_trade_opportunity': True}, 'metrics': {'risk_per_share': '$4.68', 'reward_per_share': '$12.96', 'actual_rr': '2.8:1', 'total_risk': '$47 (0.1%)', 'suggested_qty': '794', 'near_resistance': True, 'atr_distance': '6.7', 'max_risk_5pct': '$3714'}, 'issues': []}

# ============================================================
# 🎯 RISK EVALUATION REPORT
# ============================================================

# ✅ STATUS: APPROVED
# 📊 RISK SCORE: 1.25/1.50

# 📋 TRADE SETUP
#   Action:        SELL
#   Symbol:        AAPL
#   Confidence:    80%
#   Entry:         $274.13
#   Stop Loss:     $278.81
#   Take Profit:   $261.17
#   Quantity:      10 shares

# 💰 RISK METRICS
#   Risk/Share:    $4.68
#   Reward/Share:  $12.96
#   Actual R:R:    2.8:1
#   Total Risk:    $47 (0.1%)

# 📐 POSITION SIZING
#   Current Qty:   10 shares
#   Suggested Qty: 794 shares (5% risk)
#   Max Risk (5%): $3714

# 📈 TECHNICAL CONTEXT
#   Near Resistance: Yes ✅
#   ATR Distance:    6.7

# 💡 THESIS
#   The bearish sentiment score of -0.75 indicates a
#   strong negative reaction to the earnings miss,
#   creating a swing opportunity. The stock is near
#   resistance (278.81) and overbought (RSI > 70),
#   confirming the sell signal. Volatility is high (ATR >
#   20-day average), making this trade viable. Entry at
#   274.13, stop-loss at 276.5 (1% above entry),
#   take-profit at 272.2 (1% below entry).

# ✅ NO ADJUSTMENTS NEEDED

# ============================================================

# [🛡️ RISK LAYER RESULT] {'status': 'no_conflict', 'symbol': 'AAPL', 'message': 'No conflicts found - ready to trade'}

#    [🛡️ Risk Layer] Should Execute?  True
# !!! [🤝🏻 Market Access] Executing SELL {'action': 'SELL', 'confidence': 0.8, 'entry_price': 274.13, 'stop_loss': 278.80999755859375, 'take_profit': 261.1728507777623, 'qty': 10, 'risk_reward': '1:1.4', 'thesis': 'The bearish sentiment score of -0.75 indicates a strong negative reaction to the earnings miss, creating a swing opportunity. The stock is near resistance (278.81) and overbought (RSI > 70), confirming the sell signal. Volatility is high (ATR > 20-day average), making this trade viable. Entry at 274.13, stop-loss at 276.5 (1% above entry), take-profit at 272.2 (1% below entry).', 'current_stock_price': 274.57, 'ticker': 'AAPL', 'has_trade_opportunity': True}
#    [📤 API] POST http://localhost:8000/api/v1/trading/orders/bracket
#    [📤 Payload] {'symbol': 'AAPL', 'side': 'sell', 'qty': 10.0, 'entry_type': 'limit', 'take_profit_price': 261.17, 'stop_loss_price': 278.81, 'time_in_force': 'day', 'entry_price': 274.13}
#    [✅ SUCCESS] Order ID: ebe02c62-fed1-4aec-8a19-b49a4b7ad854
#    [🧾 Execution Result] {'execution_result': {'status': 'success', 'order_id': 'ebe02c62-fed1-4aec-8a19-b49a4b7ad854', 'symbol': 'AAPL', 'side': 'SELL', 'submitted_at': None, 'full_response': {'success': True, 'order_id': 'ebe02c62-fed1-4aec-8a19-b49a4b7ad854', 'status': 'pending_new', 'symbol': 'AAPL', 'order': {'id': 'ebe02c62-fed1-4aec-8a19-b49a4b7ad854', 'client_order_id': 'c48d2b56-e1bf-41e0-91c7-8b4d3fb7f759', 'created_at': '2026-02-04T16:55:39.264322Z', 'updated_at': '2026-02-04T16:55:39.265742Z', 'submitted_at': '2026-02-04T16:55:39.264322Z', 'filled_at': None, 'expired_at': None, 'expires_at': '2026-02-04T21:00:00Z', 'canceled_at': None, 'failed_at': None, 'replaced_at': None, 'replaced_by': None, 'replaces': None, 'asset_id': 'b0b6dd9d-8b9b-48a9-ba46-b9d54906e415', 'symbol': 'AAPL', 'asset_class': 'us_equity', 'notional': None, 'qty': '10', 'filled_qty': '0', 'filled_avg_price': None, 'order_class': 'bracket', 'order_type': 'limit', 'type': 'limit', 'side': 'sell', 'time_in_force': 'day', 'limit_price': '274.13', 'stop_price': None, 'status': 'pending_new', 'extended_hours': False, 'legs': [{'id': '4e2df0a9-51ce-4073-a2b6-19e44b9922ee', 'client_order_id': '96da2573-ceda-42fc-af9a-9110c4532cfb', 'created_at': '2026-02-04T16:55:39.264322Z', 'updated_at': '2026-02-04T16:55:39.265652Z', 'submitted_at': '2026-02-04T16:55:39.264322Z', 'filled_at': None, 'expired_at': None, 'expires_at': '2026-02-04T21:00:00Z', 'canceled_at': None, 'failed_at': None, 'replaced_at': None, 'replaced_by': None, 'replaces': None, 'asset_id': 'b0b6dd9d-8b9b-48a9-ba46-b9d54906e415', 'symbol': 'AAPL', 'asset_class': 'us_equity', 'notional': None, 'qty': '10', 'filled_qty': '0', 'filled_avg_price': None, 'order_class': 'bracket', 'order_type': 'limit', 'type': 'limit', 'side': 'buy', 'time_in_force': 'day', 'limit_price': '261.17', 'stop_price': None, 'status': 'held', 'extended_hours': False, 'legs': None, 'trail_percent': None, 'trail_price': None, 'hwm': None, 'position_intent': 'buy_to_close', 'ratio_qty': None}, {'id': '44f455b7-80f6-4a53-8d56-f70bf48a5cc4', 'client_order_id': '25cad759-9371-4ed2-8c48-4a6c984aecc4', 'created_at': '2026-02-04T16:55:39.264322Z', 'updated_at': '2026-02-04T16:55:39.265686Z', 'submitted_at': '2026-02-04T16:55:39.264322Z', 'filled_at': None, 'expired_at': None, 'expires_at': '2026-02-04T21:00:00Z', 'canceled_at': None, 'failed_at': None, 'replaced_at': None, 'replaced_by': None, 'replaces': None, 'asset_id': 'b0b6dd9d-8b9b-48a9-ba46-b9d54906e415', 'symbol': 'AAPL', 'asset_class': 'us_equity', 'notional': None, 'qty': '10', 'filled_qty': '0', 'filled_avg_price': None, 'order_class': 'bracket', 'order_type': 'stop', 'type': 'stop', 'side': 'buy', 'time_in_force': 'day', 'limit_price': None, 'stop_price': '278.81', 'status': 'held', 'extended_hours': False, 'legs': None, 'trail_percent': None, 'trail_price': None, 'hwm': None, 'position_intent': 'buy_to_close', 'ratio_qty': None}], 'trail_percent': None, 'trail_price': None, 'hwm': None, 'position_intent': 'sell_to_open', 'ratio_qty': None}}}}
# 📊 Final Result:
#   Action: N/A
#   Should Execute: True
#   Order Details: {'action': 'SELL', 'confidence': 0.8, 'entry_price': 274.13, 'stop_loss': 278.81, 'take_profit': 261.17, 'qty': 10.0, 'risk_reward': '1:1.4', 'thesis': 'The bearish sentiment score of -0.75 indicates a strong negative reaction to the earnings miss, creating a swing opportunity. The stock is near resistance (278.81) and overbought (RSI > 70), confirming the sell signal. Volatility is high (ATR > 20-day average), making this trade viable. Entry at 274.13, stop-loss at 276.5 (1% above entry), take-profit at 272.2 (1% below entry).', 'current_stock_price': 274.57, 'ticker': 'AAPL', 'has_trade_opportunity': True}
#   Reasoning: N/A

# ============================================================

# 🎉 All tests complete!
