from langchain_core.tools import tool

from app.schemas.chat import TradeHistory
from app.schemas.order_details import OrderDetailsResponse
from app.utils.logger import setup_logging

logger = setup_logging()


# TODO: Remove Hardcoded
async def get_order_details(order_id: str):
    order_details = {
        "id": "9eac1ca3-a44e-4f7f-a429-7dcaa07ff136",
        "client_order_id": "419131e2-9012-411d-b92d-254f4bbaf516",
        "created_at": "2026-02-10T09:57:10.111197Z",
        "updated_at": "2026-02-10T14:32:41.604397Z",
        "submitted_at": "2026-02-10T09:57:10.126584Z",
        "filled_at": "2026-02-10T14:32:41.598407Z",
        "expired_at": None,
        "expires_at": "2026-02-10T21:00:00Z",
        "canceled_at": None,
        "failed_at": None,
        "replaced_at": None,
        "replaced_by": None,
        "replaces": None,
        "asset_id": "b0b6dd9d-8b9b-48a9-ba46-b9d54906e415",
        "symbol": "AAPL",
        "asset_class": "us_equity",
        "notional": None,
        "qty": "13",
        "filled_qty": "13",
        "filled_avg_price": "274.55",
        "order_class": "bracket",
        "order_type": "limit",
        "type": "limit",
        "side": "sell",
        "time_in_force": "day",
        "limit_price": "274.5",
        "stop_price": None,
        "status": "filled",
        "extended_hours": False,
        "legs": [
            {
                "id": "863d2539-3b5f-429a-8ee3-8dc5c2f1aff0",
                "client_order_id": "e65ab734-a564-43d2-91ab-9b4e9fbe4bb4",
                "created_at": "2026-02-10T09:57:10.111197Z",
                "updated_at": "2026-02-10T21:01:24.019222Z",
                "submitted_at": "2026-02-10T14:32:42.463442Z",
                "filled_at": None,
                "expired_at": "2026-02-10T21:01:24.016471Z",
                "expires_at": "2026-02-10T21:00:00Z",
                "canceled_at": None,
                "failed_at": None,
                "replaced_at": None,
                "replaced_by": None,
                "replaces": None,
                "asset_id": "b0b6dd9d-8b9b-48a9-ba46-b9d54906e415",
                "symbol": "AAPL",
                "asset_class": "us_equity",
                "notional": None,
                "qty": "13",
                "filled_qty": "0",
                "filled_avg_price": None,
                "order_class": "bracket",
                "order_type": "limit",
                "type": "limit",
                "side": "buy",
                "time_in_force": "day",
                "limit_price": "261.42",
                "stop_price": None,
                "status": "expired",
                "extended_hours": False,
                "legs": None,
                "trail_percent": None,
                "trail_price": None,
                "hwm": None,
                "position_intent": "buy_to_close",
                "ratio_qty": None,
            },
            {
                "id": "98439fa4-3581-43d6-8903-cb3241e208b1",
                "client_order_id": "01b57a30-4aa0-473e-a3ed-df60cc82a582",
                "created_at": "2026-02-10T09:57:10.111197Z",
                "updated_at": "2026-02-10T21:01:24.019281Z",
                "submitted_at": "2026-02-10T09:57:10.111197Z",
                "filled_at": None,
                "expired_at": None,
                "expires_at": "2026-02-10T21:00:00Z",
                "canceled_at": "2026-02-10T21:01:24.019280Z",
                "failed_at": None,
                "replaced_at": None,
                "replaced_by": None,
                "replaces": None,
                "asset_id": "b0b6dd9d-8b9b-48a9-ba46-b9d54906e415",
                "symbol": "AAPL",
                "asset_class": "us_equity",
                "notional": None,
                "qty": "13",
                "filled_qty": "0",
                "filled_avg_price": None,
                "order_class": "bracket",
                "order_type": "stop",
                "type": "stop",
                "side": "buy",
                "time_in_force": "day",
                "limit_price": None,
                "stop_price": "280.65",
                "status": "canceled",
                "extended_hours": False,
                "legs": None,
                "trail_percent": None,
                "trail_price": None,
                "hwm": None,
                "position_intent": "buy_to_close",
                "ratio_qty": None,
            },
        ],
        "trail_percent": None,
        "trail_price": None,
        "hwm": None,
        "position_intent": "sell_to_open",
        "ratio_qty": None,
        "trading_agent_reasonings": "The news signal indicates a bearish sentiment with an earnings miss, which is likely to lead to a short-term price drop. The technical setup supports this thesis as the stock price is near resistance (280.6473855638201) and the RSI (84.22614707782293) is overbought. Volatility is high, but within a swing-viable regime. Entry at current stock price of 274.5 to sell at resistance level, stop-loss at support level.",
        "is_trading_agent": True,
        "risk_evaluation": {
            "risk_per_share": "$6.15",
            "reward_per_share": "$13.08",
            "actual_rr": "2.1:1",
            "total_risk": "$80 (0.1%)",
            "suggested_qty": "13",
            "near_resistance": True,
            "atr_distance": "6.5",
            "max_risk_5pct": "$3643",
            "risk_score": 1.25,
            "risk_status": "APPROVED",
        },
        "risk_adjustments_made": [
            {
                "field": "take_profit",
                "reason": "Take profit for SELL should be below entry.",
                "adjustment": "Moved TP from 243.19244305608962 to 261.42279804891035 to sit below entry and near support 2×ATR.",
            }
        ],
    }

    return (
        order_details["symbol"],
        order_details["filled_avg_price"],
        order_details["side"],
        order_details["risk_evaluation"],
        order_details["risk_adjustments_made"],
        order_details["trading_agent_reasonings"],
    )


@tool(args_schema=TradeHistory)
async def get_trade_history_details(query: str, order_id: str) -> OrderDetailsResponse:
    """
    Retrieve deep-dive technical details and trade reasoning for a specific past transaction.

    Use this tool ONLY when:
    - The user asks "why" a specific trade was made (e.g., "Why did we sell AAPL?").
    - The user asks for the technical indicators (RSI, ATR) present at the time of a specific order.
    - The user provides a specific 'order_id' for performance lookup.

    Args:
        order_id (str): The unique identifier for the trade. This is mandatory.
                        If the user has not provided an ID, do not guess;
                        ask the user for it instead.

    Returns:
        A JSON string containing:
        - ticker: The stock symbol.
        - action: The trade direction (BUY/SELL).
        - entry_price: The price at execution.
        - reasoning: The specific technical justification (e.g., RSI/ATR values).
    """

    logger.info(f"User query: {query}. Analysing history for order {order_id}")

    (
        ticker,
        avg_price,
        action,
        risk_eval,
        risk_adj,
        trading_agent_reasoning,
    ) = await get_order_details("9eac1ca3-a44e-4f7f-a429-7dcaa07ff136")

    return OrderDetailsResponse(
        ticker=ticker,
        action=action,
        entry_price=avg_price,
        reasoning=trading_agent_reasoning,
    )
