"""
Trading Database API Routes
"""
from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
import os
from app.core.trading_db_client import MongoDBClient


router = APIRouter()

mongo_client = MongoDBClient(uri=os.getenv("MONGODB_URI", "mongodb://mongo:27017"), db_name="trading_db")

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
