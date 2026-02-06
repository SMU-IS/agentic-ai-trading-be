"""
Trading Database API Routes
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import json
from app.core.trading_db_client import get_trading_db, TradingDBClient

router = APIRouter()

class DecisionCreate(BaseModel):
    order_id: str
    symbol: str
    action: str
    confidence: float
    risk_score: float
    reasonings: dict
    status: str = "open"

class DecisionResponse(BaseModel):
    order_id: str
    symbol: str
    action: Optional[str]
    confidence: Optional[float]
    risk_score: Optional[float]
    reasonings: dict
    pnl: Optional[float]
    status: str
    created_at: str


async def get_db_conn() -> TradingDBClient:
    return await get_trading_db()


@router.post("/", response_model=dict, status_code=201)
async def create_decision(decision: DecisionCreate, db: TradingDBClient = Depends(get_db_conn)):
    """Store new trading decision"""
    success = await db.store_decision(
        decision.order_id, 
        decision.model_dump()
    )
    
    if success:
        return {"message": "Decision stored", "order_id": decision.order_id}
    raise HTTPException(status_code=500, detail="Failed to store decision")

@router.get("/{order_id}", response_model=DecisionResponse)
async def get_decision(order_id: str, db: TradingDBClient = Depends(get_db_conn)):
    """Get decision by order_id"""
    decision = await db.get_decision(order_id)
    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found")
    return decision

@router.get("/", response_model=dict)
async def list_decisions(
    symbol: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=1000),
    db: TradingDBClient = Depends(get_trading_db)
):
    """List recent decisions (front-end dashboard)"""
    decisions = await db.get_recent_decisions(symbol, limit, status)
    return {
        "decisions": decisions,
        "count": len(decisions),
        "filters": {"symbol": symbol, "status": status, "limit": limit}
    }

@router.get("/symbol/{symbol}", response_model=dict)
async def decisions_by_symbol(symbol: str, limit: int = Query(50), db: TradingDBClient = Depends(get_db_conn)):
    """Symbol-specific decisions"""
    decisions = await db.get_recent_decisions(symbol, limit)
    return {
        "symbol": symbol,
        "decisions": decisions,
        "count": len(decisions)
    }

@router.put("/{order_id}/pnl")
async def update_decision_pnl(order_id: str, pnl: float, status: str = "closed", db: TradingDBClient = Depends(get_db_conn)):
    """Update PnL after trade execution"""
    await db.update_pnl(order_id, pnl, status)
    return {"message": f"Updated PnL: {pnl}, Status: {status}"}

@router.delete("/{order_id}")
async def delete_decision(order_id: str, db: TradingDBClient = Depends(get_db_conn)):
    """Delete decision (admin only)"""
    async with db.get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM decisions WHERE order_id = $1", order_id
        )
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Decision not found")
        return {"message": "Decision deleted"}