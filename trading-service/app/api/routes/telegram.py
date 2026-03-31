from typing import Dict, Any

from fastapi import APIRouter, HTTPException

from app.core.telegram_service import post_signal, post_order

router = APIRouter()


@router.post("/signal", status_code=200)
async def send_signal(payload: Dict[str, Any]):
    """
    Post a trading signal to the Telegram Signals topic.

    Expected keys: ticker, action, confidence, entry_price, thesis
    """
    try:
        await post_signal(payload)
        return {"status": "sent", "topic": "signals"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/order", status_code=200)
async def send_order(payload: Dict[str, Any]):
    """
    Post an order result to the Telegram Orders topic.

    Expected keys: status, symbol, side, order_id, user_id, profile,
                   risk_evaluation, confidence
    """
    try:
        await post_order(payload)
        return {"status": "sent", "topic": "orders"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
