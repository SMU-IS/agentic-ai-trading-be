"""
Trading Database API Routes
"""
from typing import List, Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, Path
from app.core.trading_db_client import MongoDBClient
from app.core.services import services
from app.api.schemas import DeepAnalysis
from bson import ObjectId

router = APIRouter()

# mongo_client = MongoDBClient(uri=os.getenv("MONGODB_URI", "mongodb://mongo:27017"), db_name="trading_db")
mongo_client: MongoDBClient = services.trading_db

@router.post("/orders")
def store_orders(orders: List[Dict], client: MongoDBClient = Depends(lambda: mongo_client)):
    result = client.store_orders_bulk(orders)
    return result

@router.get("/orders")
def get_orders(symbol: Optional[str] = None, limit: int = 50, 
               client: MongoDBClient = Depends(lambda: mongo_client)):
    return client.get_orders(symbol, limit)

@router.get("/orders/{order_id}")
def get_order_by_id(order_id: str, client: MongoDBClient = Depends(lambda: mongo_client)):
    order = client.get_order_by_id(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order
    
    
#  Signals
@router.post("/signals/", status_code=201)
async def create_signal(
    signal: DeepAnalysis,  # Or Signal(model_validate compatible)
    client: MongoDBClient = Depends(lambda: mongo_client)
):
    """Create a new trading signal."""
    signal_dict = signal.model_dump()
    result = client.store_signal(signal_dict)
    if not result["success"]:
        raise HTTPException(status_code=500, detail="Failed to store signal")
    return result

@router.get("/signals/", response_model=List[DeepAnalysis])
async def get_signals(
    client: MongoDBClient = Depends(lambda: mongo_client)
):
    """Get all trading signals."""
    docs = client.get_signals()
    return [DeepAnalysis.model_validate(doc) for doc in docs]

@router.get("/signals/ticker/{ticker}", response_model=List[DeepAnalysis])
async def get_signal_by_ticker(
    ticker: str,
    client: MongoDBClient = Depends(lambda: mongo_client)
):
    """Get trading signals by ticker."""
    docs = client.get_signals(ticker=ticker)
    if not docs:
        raise HTTPException(status_code=404, detail=f"No signals for {ticker}")
    return [DeepAnalysis.model_validate(doc) for doc in docs]

@router.get("/signals/{signal_id}", response_model=Optional[DeepAnalysis])
async def get_signal_by_id(
    signal_id: str = Path(..., description="MongoDB _id as hex string"),
    client: MongoDBClient = Depends(lambda: mongo_client)
):
    """Get a single trading signal by MongoDB _id."""
    if not ObjectId.is_valid(signal_id):
        raise HTTPException(status_code=400, detail="Invalid MongoDB ObjectId")
    doc = client.get_signal_by_id(signal_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Signal not found")
    return DeepAnalysis.model_validate(doc)

@router.get("/trading-accounts", response_model=list[dict])
async def get_all_trading_accounts(
    client: MongoDBClient = Depends(lambda: mongo_client)
) -> list[dict]:
    try:
        result = client.get_all_trading_accounts()
        return result
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e))

