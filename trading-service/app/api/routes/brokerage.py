from datetime import datetime
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.broker_client import AlpacaBrokerClient, create_broker_client
from app.api.schemas import (
    MarketOrderRequestBody,
    LimitOrderRequestBody,
    StopOrderRequestBody,
    StopLimitOrderRequestBody,
    BracketOrderRequestBody,
    ClosePositionRequestBody,
    CloseAllPositionsRequestBody,
)

router = APIRouter()


# Dependency to get a broker instance (can be singleton or factory)
def get_broker() -> AlpacaBrokerClient:
    return create_broker_client()


# ---------- Health ----------

@router.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


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
    broker: AlpacaBrokerClient = Depends(get_broker),
) -> List[Dict[str, Any]]:
    try:
        return broker.list_all_orders(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/orders/{order_id}")
def get_order(
    order_id: str,
    broker: AlpacaBrokerClient = Depends(get_broker),
) -> Dict[str, Any]:
    try:
        return broker.get_order(order_id)
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


@router.post("/orders/bracket", status_code=201)
def create_bracket_order(
    body: BracketOrderRequestBody,
    broker: AlpacaBrokerClient = Depends(get_broker),
) -> Dict[str, Any]:
    try:
        data = broker.submit_bracket_order(
            symbol=body.symbol,
            side=body.side,
            qty=body.qty,
            entry_type=body.entry_type,
            entry_price=body.entry_price,
            take_profit_price=body.take_profit_price,
            stop_loss_price=body.stop_loss_price,
            time_in_force=body.time_in_force,
        )
        return data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


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