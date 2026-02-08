import pymongo
from typing import List, Dict, Any, Optional
from bson import ObjectId
from copy import deepcopy

class MongoDBClient:
    def __init__(self, uri: str = "mongodb://mongo:27017", db_name: str = "trading_db"):
        self.client = pymongo.MongoClient(uri)
        self.db = self.client[db_name]
        self.orders = self.db.orders
        
    def store_orders_bulk(self, orders: List[Dict[str, Any]]) -> Dict[str, int]:
        """Store multiple orders (synchronous)"""
        if not orders:
            return {"success": 0, "failed": 0}
        
        # Copy to avoid mutation by insert_many
        orders_copy = deepcopy(orders)
        result = self.orders.insert_many(orders_copy, ordered=False)
        return {"success": len(result.inserted_ids), "failed": 0}
    
    def get_orders(self, symbol: str = None, limit: int = 50) -> List[Dict]:
        """Query orders (synchronous)"""
        query = {} if symbol is None else {"symbol": symbol}
        cursor = self.orders.find(query).sort("created_at", -1).limit(limit)
        
        # Convert ObjectIds to strings for JSON
        return [{"_id": str(doc["_id"]), **{k: v for k, v in doc.items() if k != "_id"}} 
                for doc in cursor]
    
    def get_order_by_id(self, order_id: str) -> Optional[Dict]:
        """Get single order by ID"""
        doc = self.orders.find_one({"_id": ObjectId(order_id)})
        if doc:
            doc["_id"] = str(doc["_id"])
            return doc
        return None