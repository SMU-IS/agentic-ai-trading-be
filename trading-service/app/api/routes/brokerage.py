import logging
import time
import time
from datetime import date, datetime
from datetime import time as dt_time
from datetime import timezone
from typing import Any, Dict, List, Optional, Tuple

from app.api.schemas import (
    BracketOrderRequestBody,
    CloseAllPositionsRequestBody,
    ClosePositionRequestBody,
    LimitOrderRequestBody,
    MarketOrderRequestBody,
    PortfolioHistoryResponse,
    StopLimitOrderRequestBody,
    StopOrderRequestBody,
)
from app.core.broker_client import AlpacaBrokerClient, create_broker_client
from app.core.services import services
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field


# Data models for latest trades
class LatestTradeResponse(BaseModel):
    symbol: str
    price: float
    size: int
    exchange: str
    conditions: List[str]
    timestamp: Optional[str]
    id: str
    tape: Optional[str]


class LatestTradesResponse(BaseModel):
    data: Dict[str, Dict[str, Any]]


# Data model for latest quote
class LatestQuoteResponse(BaseModel):
    symbol: str
    bid_price: float
    bid_size: int
    ask_price: float
    ask_size: int
    timestamp: Optional[str]
    conditions: List[str]
    tape: Optional[str]


class LatestQuotesResponse(BaseModel):
    data: Dict[str, Dict[str, Any]]


class CancelOrdersRequest(BaseModel):
    order_ids: Optional[List[str]] = None
    cancel_all: bool = False


class ConflictCheckRequest(BaseModel):
    symbol: str = Field(..., description="Stock symbol")
    intended_side: str = Field(..., pattern="^(buy|sell)$")
    intended_qty: float = Field(..., gt=0)
    auto_resolve: bool = Field(False, description="Auto close/cancel conflicts")


class PnLResponse(BaseModel):
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    start_equity: Optional[float] = None
    end_equity: Optional[float] = None
    timeframe: Optional[str] = None
    error: Optional[str] = None


class UserRequest(BaseModel):
    user_id: str = "agent-A"  # Default user


router = APIRouter()

# ── In-memory TTL cache for /orders/all ───────────────────────────────────────
_orders_cache: Dict[Tuple[str, int], Tuple[float, List]] = {}
_CACHE_TTL = 30  # seconds


def _get_cached_orders(user_id: str, limit: int) -> List | None:
    entry = _orders_cache.get((user_id, limit))
    if entry and (time.time() - entry[0]) < _CACHE_TTL:
        return entry[1]
    return None


def _set_cached_orders(user_id: str, limit: int, data: List) -> None:
    _orders_cache[(user_id, limit)] = (time.time(), data)


def _invalidate_orders_cache(user_id: str) -> None:
    keys = [k for k in _orders_cache if k[0] == user_id]
    for k in keys:
        del _orders_cache[k]
    print(f"   [🗑️  Cache] Orders cache invalidated for user={user_id}")


# ──────────────────────────────────────────────────────────────────────────────


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Dependency to get a broker instance (can be singleton or factory)
def get_broker(
    x_user_id: str = Header(default="agent-A"),
) -> AlpacaBrokerClient:
    try:
        print("fetching for user", x_user_id)
        api_key, api_secret, paper = services.trading_db._load_user_account_from_mongo(
            x_user_id
        )
        return create_broker_client(api_key, api_secret, paper)
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------- Health ----------


@router.get("/")
def health() -> Dict[str, str]:
    return {"status": "Alpacca service is healthy"}


# ---------- Debugging / info ----------
@router.get("/debug_feed")
def debug_feed(broker: AlpacaBrokerClient = Depends(get_broker)):
    quote = broker.get_latest_quote("AAPL")
    return {
        "feed_used": "SIP" if quote.get("exchange") in ["Q", "V", "N"] else "IEX",
        "exchange": quote.get("exchange"),
        "sample_quote": quote,
    }


# ---------- Account / positions ----------


@router.get("/account")
def get_account(
    broker: AlpacaBrokerClient = Depends(get_broker),
) -> Dict[str, Any]:
    try:
        return broker.get_account()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions")
def get_positions(
    broker: AlpacaBrokerClient = Depends(get_broker),
) -> List[Dict[str, Any]]:
    try:
        return broker.get_open_positions()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions/{symbol}")
def get_position(
    symbol: str,
    broker: AlpacaBrokerClient = Depends(get_broker),
) -> Dict[str, Any]:
    try:
        data = broker.get_position(symbol)
        if data is None:
            raise HTTPException(status_code=404, detail="no open position")
        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------- Orders (list / get) ----------


@router.get("/orders")
def list_open_orders(
    broker: AlpacaBrokerClient = Depends(get_broker),
) -> List[Dict[str, Any]]:
    try:
        return broker.list_open_orders()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/orders/all")
def list_all_orders(
    limit: int = Query(200, ge=1, le=500),
    after: Optional[date] = Query(None),
    until: Optional[date] = Query(None),
    broker: AlpacaBrokerClient = Depends(get_broker),
    x_user_id: str = Header(default="agent-A"),
) -> List[Dict[str, Any]]:
    try:
        after_dt = datetime.combine(after, dt_time.min, tzinfo=timezone.utc) if after else None
        until_dt = datetime.combine(until, dt_time.max, tzinfo=timezone.utc) if until else None

        use_cache = not after_dt and not until_dt
        if use_cache:
            cached = _get_cached_orders(x_user_id, limit)
            if cached is not None:
                print(f"   [⚡ Cache HIT] user={x_user_id} | {len(cached)} orders")
                return cached

        all_orders = broker.list_all_orders(limit=limit, after=after_dt, until=until_dt)
        order_ids = [str(order["id"]) for order in all_orders]

        reasonings = services.trading_db.get_reasonings_batch(order_ids)
        print(
            f"   [📋 Orders] user={x_user_id} | Fetched {len(all_orders)} orders | {len(reasonings)} with agent reasoning"
        )

        for order in all_orders:
            r = reasonings.get(str(order["id"]), {})
            if r.get("reasonings") is not None:
                order["trading_agent_reasonings"] = r.get("reasonings", "")
                order["is_trading_agent"] = True
                order["risk_evaluation"] = r.get("risk_evaluation", {})
                order["risk_adjustments_made"] = r.get("risk_adjustments_made", [])
                order["signal_data"] = r.get("signal_data")
                order["closed_position"] = r.get("closed_position")
            else:
                order["trading_agent_reasonings"] = None
                order["is_trading_agent"] = False

        if use_cache:
            _set_cached_orders(x_user_id, limit, all_orders)
            print(f"   [💾 Cache SET] user={x_user_id} | TTL={_CACHE_TTL}s")
        return all_orders
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/orders/{order_id}")
def get_order(
    order_id: str,
    broker: AlpacaBrokerClient = Depends(get_broker),
) -> Dict[str, Any]:
    try:
        order_info = broker.get_order(order_id)
        order_ids = [str(order_info["id"])]
        reasonings = services.trading_db.get_reasonings_batch(order_ids)

        if reasonings.get(order_id, {}).get("reasonings", None) is not None:
            order_info["trading_agent_reasonings"] = reasonings.get(order_id, {}).get(
                "reasonings", ""
            )
            order_info["is_trading_agent"] = True
            order_info["risk_evaluation"] = reasonings.get(order_id, {}).get(
                "risk_evaluation", {}
            )
            order_info["risk_adjustments_made"] = reasonings.get(order_id, {}).get(
                "risk_adjustments_made", []
            )
        else:
            order_info["trading_agent_reasonings"] = None
            order_info["is_trading_agent"] = False
        return order_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------- Orders (create) ----------


@router.post("/orders/market", status_code=201)
def create_market_order(
    body: MarketOrderRequestBody,
    broker: AlpacaBrokerClient = Depends(get_broker),
) -> Dict[str, Any]:
    try:
        data = broker.submit_market_order(
            symbol=body.symbol,
            side=body.side,
            qty=body.qty,
            notional=body.notional,
            time_in_force=body.time_in_force,
        )
        return data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/orders/limit", status_code=201)
def create_limit_order(
    body: LimitOrderRequestBody,
    broker: AlpacaBrokerClient = Depends(get_broker),
) -> Dict[str, Any]:
    try:
        data = broker.submit_limit_order(
            symbol=body.symbol,
            side=body.side,
            limit_price=body.limit_price,
            qty=body.qty,
            notional=body.notional,
            time_in_force=body.time_in_force,
            extended_hours=body.extended_hours,
        )
        return data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/orders/stop", status_code=201)
def create_stop_order(
    body: StopOrderRequestBody,
    broker: AlpacaBrokerClient = Depends(get_broker),
) -> Dict[str, Any]:
    try:
        data = broker.submit_stop_order(
            symbol=body.symbol,
            side=body.side,
            stop_price=body.stop_price,
            qty=body.qty,
            notional=body.notional,
            time_in_force=body.time_in_force,
        )
        return data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/orders/stop_limit", status_code=201)
def create_stop_limit_order(
    body: StopLimitOrderRequestBody,
    broker: AlpacaBrokerClient = Depends(get_broker),
) -> Dict[str, Any]:
    try:
        data = broker.submit_stop_limit_order(
            symbol=body.symbol,
            side=body.side,
            stop_price=body.stop_price,
            limit_price=body.limit_price,
            qty=body.qty,
            notional=body.notional,
            time_in_force=body.time_in_force,
        )
        return data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/orders/bracket", status_code=201, response_model=Dict[str, Any])
def create_bracket_order(
    body: BracketOrderRequestBody,
    broker: AlpacaBrokerClient = Depends(get_broker),
    x_user_id: str = Header(default="agent-A"),
) -> Dict[str, Any]:
    """
    Submit bracket order (market/limit entry + take profit + stop loss).

    - Validates parameters via Pydantic schema
    - Uses Broker API format (take_profit_price/stop_loss_price)
    - Returns full order response from Alpaca
    """
    try:
        # Convert enums to strings for broker method (if needed)
        order_data = broker.submit_bracket_order(
            symbol=body.symbol,
            side=body.side.value,  # Enum -> str
            qty=float(body.qty),  # Ensure float
            entry_type=body.entry_type.value,  # Enum -> str
            entry_price=body.entry_price,
            take_profit_price=float(body.take_profit_price),
            stop_loss_price=float(body.stop_loss_price),
            time_in_force=body.time_in_force.value,  # Enum -> str
        )

        # Log order ID for tracking
        logger.info(
            f"Bracket order submitted: {order_data.get('id')} for {body.symbol}"
        )

        _invalidate_orders_cache(x_user_id)
        return {
            "success": True,
            "order_id": order_data["id"],
            "status": order_data["status"],
            "symbol": body.symbol,
            "order": order_data,
        }

    except ValueError as e:
        # Validation/business logic errors
        raise HTTPException(
            status_code=400, detail=f"Invalid order parameters: {str(e)}"
        )
    except Exception as e:
        # Alpaca API errors
        logger.error(f"Bracket order failed: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Order submission failed: {str(e)}"
        )


# ---------- Positions closing / emergency ----------


@router.post("/positions/{symbol}/close")
def close_position(
    symbol: str,
    body: ClosePositionRequestBody,
    broker: AlpacaBrokerClient = Depends(get_broker),
) -> Dict[str, Any]:
    try:
        data = broker.close_position(
            symbol=symbol,
            percentage=body.percentage,
            qty=body.qty,
        )
        return data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/positions/close_all")
def close_all_positions(
    body: CloseAllPositionsRequestBody,
    broker: AlpacaBrokerClient = Depends(get_broker),
) -> List[Dict[str, Any]]:
    try:
        data = broker.close_all_positions(cancel_orders=body.cancel_orders)
        return data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/orders/cancel")
async def cancel_orders(
    req: CancelOrdersRequest, broker: AlpacaBrokerClient = Depends(get_broker)
) -> Dict[str, Any]:
    """
    Cancel specific orders by ID or all open orders.
    """
    try:
        result = broker.cancel_orders(
            order_ids=req.order_ids, cancel_all=req.cancel_all
        )
        _invalidate_orders_cache()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------- Conflict checking / resolution ----------
@router.post("/orders/check-conflicts")
async def check_conflicts(
    req: ConflictCheckRequest, broker: AlpacaBrokerClient = Depends(get_broker)
) -> Dict[str, Any]:
    """
    Check for conflicting positions/orders before placing new trade.

    Returns conflicts found + required cleanup actions.
    """
    result = broker.check_conflicting_positions(
        symbol=req.symbol,
        intended_side=req.intended_side,
        intended_qty=req.intended_qty,
    )
    return result


@router.post("/orders/resolve-conflicts")
async def resolve_conflicts(
    req: ConflictCheckRequest, broker: AlpacaBrokerClient = Depends(get_broker)
) -> Dict[str, Any]:
    """
    Check conflicts AND auto-resolve (close position + cancel orders).

    Use before submitting new bracket order to ensure clean entry.
    """
    result = broker.resolve_conflicts(
        symbol=req.symbol,
        intended_side=req.intended_side,
        intended_qty=req.intended_qty,
        auto_resolve=req.auto_resolve,
    )
    return result


# ---------- Convenience ----------


@router.get("/account/equity_cash")
def equity_cash(
    broker: AlpacaBrokerClient = Depends(get_broker),
) -> Dict[str, float]:
    try:
        return broker.get_equity_and_cash()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/account/trading_blocked")
def trading_blocked(
    broker: AlpacaBrokerClient = Depends(get_broker),
) -> Dict[str, bool]:
    try:
        blocked = broker.is_trading_blocked()
        return {"trading_blocked": blocked}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------- Latest Trades ----------
# --------------------------------
# Get market data for latest trades per symbol
@router.get("/latest_trade/{symbol}", response_model=LatestTradeResponse)
async def get_latest_trade(
    symbol: str, broker: AlpacaBrokerClient = Depends(get_broker)
) -> LatestTradeResponse:
    """
    Get the most recent trade for a symbol.
    Example: /api/brokerage/latest_trade/AAPL
    """
    result = broker.get_latest_trade(symbol)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return LatestTradeResponse(**result)


# ---------- Latest Quotes ----------
@router.get("/latest_quote/{symbol}", response_model=LatestQuoteResponse)
async def get_latest_quote(
    symbol: str, broker: AlpacaBrokerClient = Depends(get_broker)
) -> LatestQuoteResponse:
    """
    Get the most recent quote for a symbol.
    /api/brokerage/latest_quote/AAPL
    """
    result = broker.get_latest_quote(symbol)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return LatestQuoteResponse(**result)


@router.get("/portfolio_history", response_model=PortfolioHistoryResponse)
async def get_portfolio_history(
    broker: AlpacaBrokerClient = Depends(get_broker),
) -> PortfolioHistoryResponse:
    """
    Portfolio equity history (simple array format).
    """
    result = broker.get_portfolio_history()

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return PortfolioHistoryResponse(**result)


@router.get("/pnl", response_model=PnLResponse)  # Changed endpoint to /pnl
async def get_overall_pnl(
    broker: AlpacaBrokerClient = Depends(get_broker),
) -> PnLResponse:
    """
    1-year overall PnL (start vs end equity).
    Uses portfolio history with period="1Year".
    """
    result = broker.get_overall_pnl()

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return PnLResponse(**result)
