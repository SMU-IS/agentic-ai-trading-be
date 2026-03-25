from dataclasses import dataclass

from app.config import settings
from app.core.broker_client import AlpacaBrokerClient, create_broker_client
from app.core.trading_db_client import MongoDBClient
from app.core.yahoo_client import YahooClient

mongo_client = MongoDBClient(uri=settings.mongodb_url, db_name="trading_db")


@dataclass
class Services:
    brokerage: AlpacaBrokerClient = None
    trading_db: MongoDBClient = None
    yahoo: YahooClient = None

    @classmethod
    def get(cls) -> "Services":
        if not hasattr(cls, "_instance"):
            cls._instance = Services()
        return cls._instance


# Initialize once
services = Services.get()
services.trading_db = mongo_client
# services.brokerage = create_broker_client(services.trading_db)
services.yahoo = YahooClient()
