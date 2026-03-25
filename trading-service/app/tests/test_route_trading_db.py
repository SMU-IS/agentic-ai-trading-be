"""
Simple pytest for MongoDBClient
"""
import pymongo
from unittest.mock import MagicMock, patch
from bson import ObjectId

from app.core.trading_db_client import MongoDBClient  # adjust import path if needed


class TestMongoDBClient:
    def setup_method(self):
        self.client_mock = MagicMock(spec=pymongo.MongoClient)
        self.db_mock = MagicMock()
        self.orders_mock = MagicMock()
        self.signals_mock = MagicMock()

        self.client_mock.__getitem__.return_value = self.db_mock
        self.db_mock.__getitem__.side_effect = lambda name: {
            "orders": self.orders_mock,
            "signals": self.signals_mock,
        }[name]
    
    def test_store_orders_bulk_empty(self):
        with patch("pymongo.MongoClient", return_value=self.client_mock):
            client = MongoDBClient()
            result = client.store_orders_bulk([])
        assert result == {"success": 0, "failed": 0}
        
    def test_store_signal_success(self):
        signal = {"ticker": "AAPL", "signal_type": "buy"}
        result = MagicMock()
        result.inserted_id = ObjectId()

        self.signals_mock.insert_one.return_value = result

        with patch("pymongo.MongoClient", return_value=self.client_mock):
            client = MongoDBClient()
            res = client.store_signal(signal)

        assert res["success"] is True
        assert isinstance(res["id"], str)
