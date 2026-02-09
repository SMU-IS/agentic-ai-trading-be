from typing import Dict, Any
from dataclasses import dataclass
from app.core.broker_client import create_broker_client, AlpacaBrokerClient
from app.core.trading_db_client import MongoDBClient
from app.core.yahoo_client import YahooClient
import os


mongo_client = MongoDBClient(uri=os.getenv("MONGODB_URI", "mongodb://mongo:27017"), db_name="trading_db")

@dataclass
class Services:
    brokerage: AlpacaBrokerClient = None
    trading_db: MongoDBClient = None
    yahoo: YahooClient = None
    
    @classmethod
    def get(cls) -> 'Services':
        if not hasattr(cls, '_instance'):
            cls._instance = Services()
        return cls._instance

# Initialize once
services = Services.get()
services.brokerage = create_broker_client()
services.trading_db = mongo_client
services.yahoo = YahooClient()