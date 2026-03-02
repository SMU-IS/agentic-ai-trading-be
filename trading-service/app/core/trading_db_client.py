import pymongo
from typing import List, Dict, Any, Optional
from copy import deepcopy
from bson import ObjectId

class MongoDBClient:
    def __init__(self, uri: str = "mongodb://mongo:27017", db_name: str = "trading_db"):
        self.client = pymongo.MongoClient(uri, uuidRepresentation="standard")
        self.db = self.client[db_name]
        self.orders = self.db.orders
        self.signals = self.db.signals 
        
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
        """Get single order by custom order_id field"""
        doc = self.orders.find_one({"order_id": order_id})  # Changed from _id to order_id
        if doc:
            if "_id" in doc:
                doc["_id"] = str(doc["_id"])  # Still convert MongoDB _id to string
            return doc
        return None
    
    def get_reasonings_batch(self, order_ids: List[str]) -> Dict[str, Dict]:
        """Get reasonings for multiple order_ids {order_id: {reasonings: "..."}}"""
        docs = self.orders.find({"order_id": {"$in": order_ids}})
        
        result = {}
        for doc in docs:
            order_id = doc['order_id']
            # Inline ObjectId → str conversion (only _id field)
            serialized_doc = doc.copy()
            if '_id' in serialized_doc:
                serialized_doc['_id'] = str(serialized_doc['_id'])
            
            # ✅ Check for signal_id and fetch from signals
            if 'signal_id' in serialized_doc:
                signal_id = serialized_doc['signal_id']
                signal_doc = self.signals.find_one({"_id": ObjectId(signal_id)})
                if signal_doc:
                    # Convert ObjectId to string
                    signal_doc = signal_doc.copy()
                    if '_id' in signal_doc:
                        signal_doc['_id'] = str(signal_doc['_id'])
                    serialized_doc['signal_data'] = signal_doc
            
            result[order_id] = serialized_doc

        return result
    
    # Signals - From aggregator service
    def store_signal(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """Store single trading signal."""
        signal_copy = deepcopy(signal)
        result = self.signals.insert_one(signal_copy)
        return {"success": bool(result.inserted_id), "id": str(result.inserted_id) if result.inserted_id else None}

    # def get_signals(self, ticker: str = None) -> List[Dict[str, Any]]:
    #     """Retrieve signals, optionally filtered by ticker. Includes _id as string."""
    #     query = {} if ticker is None else {"ticker": ticker}
    #     docs = list(self.signals.find(query))  # Remove projection to include _id
        
    #     # Convert ObjectId to string in each doc
    #     for doc in docs:
    #         if "_id" in doc:
    #             doc["id"] = str(doc["_id"])
        
    #     return docs

    def get_signals(self, ticker: str = None) -> List[Dict[str, Any]]:
        """Retrieve signals, optionally filtered by ticker. Includes id (str) and timestamp (ISO)."""
        query = {} if ticker is None else {"ticker": ticker}
        docs = list(self.signals.find(query))  # Remove projection to include _id
        print("GETTING SIGNALS")
        # Convert ObjectId to string and add timestamp in each doc
        for doc in docs:
            if "_id" in doc:
                oid = doc["_id"]
                doc["id"] = str(oid)
                doc["timestamp"] = oid.generation_time.isoformat()  # ISO string like "2026-02-13T10:30:00"
                
        return docs
    
    def get_signal_by_id(self, signal_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single signal by MongoDB _id (as hex string)."""
        try:
            doc = self.signals.find_one({"_id": ObjectId(signal_id)})
            if doc:
                doc["id"] = str(doc["_id"])  # Convert ObjectId to string for JSON
            return doc
        except Exception:
            return None
        

    def get_batch_signals_by_ids(self, signal_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        if not signal_ids:
            return {}
        
        try:
            # ✅ Query by custom 'id' field (stores UUID strings)
            cursor = self.signals.find(
                {"order_id": {"$in": signal_ids}}  # Not _id!
            )
            
            # Map signal_id → document
            id_to_doc = {}
            for doc in cursor:
                signal_id = doc.get("id")  # String UUID
                if signal_id:
                    id_to_doc[signal_id] = doc
            
            return id_to_doc
            
        except Exception as e:
            print(f"Batch signal lookup error: {e}")
            return {}