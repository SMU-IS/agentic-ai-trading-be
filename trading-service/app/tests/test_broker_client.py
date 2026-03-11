import pytest
from unittest.mock import MagicMock, patch, Mock
from typing import Dict, Any

from app.core.broker_client import AlpacaBrokerClient, BrokerConfig, GetOrdersRequest # adjust import path

class TestAlpacaBrokerClient:
    def setup_method(self):
        self.mock_config = Mock(spec=BrokerConfig)
        self.mock_config.api_key = "test-key"
        self.mock_config.api_secret = "test-secret"
        self.mock_config.paper = True

        self.mock_trading_client = MagicMock()
        self.mock_stock_data_client = MagicMock()

    @patch("app.core.broker_client._load_config_from_env")
    @patch("app.core.broker_client.TradingClient")
    @patch("app.core.broker_client.StockHistoricalDataClient")
    def test_init_uses_config_from_env_if_none(
        self,
        mock_stock_data_client,
        mock_trading_client,
        mock_load_config,
    ):
        mock_load_config.return_value = self.mock_config
        mock_trading_client.return_value = self.mock_trading_client
        mock_stock_data_client.return_value = self.mock_stock_data_client

        broker = AlpacaBrokerClient()

        assert broker.config == self.mock_config
        mock_trading_client.assert_called_once_with(
            api_key=self.mock_config.api_key,
            secret_key=self.mock_config.api_secret,
            paper=self.mock_config.paper,
        )
        mock_stock_data_client.assert_called_once_with(
            api_key=self.mock_config.api_key,
            secret_key=self.mock_config.api_secret,
        )
        assert broker.client == self.mock_trading_client
        assert broker.data_client == self.mock_stock_data_client

    @patch("app.core.broker_client.TradingClient")
    @patch("app.core.broker_client.StockHistoricalDataClient")
    def test_init_uses_passed_config(
        self,
        mock_stock_data_client,
        mock_trading_client,
    ):
        mock_trading_client.return_value = self.mock_trading_client
        mock_stock_data_client.return_value = self.mock_stock_data_client

        broker = AlpacaBrokerClient(config=self.mock_config)

        assert broker.config == self.mock_config
        mock_trading_client.assert_called_once_with(
            api_key=self.mock_config.api_key,
            secret_key=self.mock_config.api_secret,
            paper=self.mock_config.paper,
        )
        mock_stock_data_client.assert_called_once_with(
            api_key=self.mock_config.api_key,
            secret_key=self.mock_config.api_secret,
        )
        
    
    def test_get_open_positions_empty(self):
        broker = AlpacaBrokerClient.__new__(AlpacaBrokerClient)
        broker.client = MagicMock()
        broker.client.get_all_positions.return_value = []

        result = broker.get_open_positions()

        assert isinstance(result, list)
        assert result == []
        
    def test_get_open_positions_non_empty(self):
        mock_position1 = Mock()
        mock_position1.__dict__ = {
            "symbol": "AAPL",
            "qty": 10,
            "avg_entry_price": 150.0,
        }
        mock_position2 = Mock()
        mock_position2.__dict__ = {
            "symbol": "GOOGL",
            "qty": 5,
            "avg_entry_price": 2800.0,
        }

        broker = AlpacaBrokerClient.__new__(AlpacaBrokerClient)
        broker.client = MagicMock()
        broker.client.get_all_positions.return_value = [mock_position1, mock_position2]

        result = broker.get_open_positions()

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["symbol"] == "AAPL"
        assert result[1]["symbol"] == "GOOGL"
        broker.client.get_all_positions.assert_called_once()
    
    def test_list_open_orders_empty(self):
        broker = AlpacaBrokerClient.__new__(AlpacaBrokerClient)
        broker.client = MagicMock()
        broker.client.get_orders.return_value = []

        result = broker.list_open_orders()

        assert isinstance(result, list)
        assert result == []
        broker.client.get_orders.assert_called_once()
        arg = broker.client.get_orders.call_args[1]["filter"]
        assert isinstance(arg, GetOrdersRequest)
        assert arg.status == "open"
        
    def test_list_all_orders_empty(self):
        broker = AlpacaBrokerClient.__new__(AlpacaBrokerClient)
        broker.client = MagicMock()
        broker.client.get_orders.return_value = []

        result = broker.list_all_orders(limit=200)

        assert isinstance(result, list)
        assert result == []
        broker.client.get_orders.assert_called_once()
        arg = broker.client.get_orders.call_args[1]["filter"]
        assert isinstance(arg, GetOrdersRequest)
        assert arg.status == "all"
        assert arg.limit == 200
    
    def test_submit_market_order_with_qty(self):
        # Arrange
        class FakeOrder:
            pass

        order_obj = FakeOrder()
        order_obj.id = "market123"
        order_obj.symbol = "AAPL"
        order_obj.side = "buy"
        order_obj.qty = 10
        order_obj.time_in_force = "day"

        # Mock the broker: real method, but client and helpers mocked
        broker = AlpacaBrokerClient.__new__(AlpacaBrokerClient)
        broker._side_from_str = lambda x: x
        broker._tif_from_str = lambda x: x
        broker.client = MagicMock()
        broker.client.submit_order.return_value = order_obj

        # Act
        result = broker.submit_market_order(
            symbol="AAPL",
            side="buy",
            qty=10,
            time_in_force="day",
        )

        # Assert
        assert isinstance(result, dict)
        assert result["id"] == "market123"
        assert result["symbol"] == "AAPL"
        assert result["qty"] == 10
        broker.client.submit_order.assert_called_once()
        call_arg = broker.client.submit_order.call_args.kwargs["order_data"]
        assert call_arg.symbol == "AAPL"
        assert call_arg.qty == 10
        assert call_arg.notional is None
    
    def test_submit_limit_order_with_qty(self):
        class FakeOrder:
            pass

        order_obj = FakeOrder()
        order_obj.id = "limit123"
        order_obj.symbol = "AAPL"
        order_obj.side = "buy"
        order_obj.qty = 10
        order_obj.limit_price = 149.5
        order_obj.time_in_force = "day"
        order_obj.extended_hours = True

        broker = AlpacaBrokerClient.__new__(AlpacaBrokerClient)
        broker._side_from_str = lambda x: x
        broker._tif_from_str = lambda x: x
        broker.client = MagicMock()
        broker.client.submit_order.return_value = order_obj

        result = broker.submit_limit_order(
            symbol="AAPL",
            side="buy",
            limit_price=149.5,
            qty=10,
            time_in_force="day",
            extended_hours=True,
        )

        assert isinstance(result, dict)
        assert result["id"] == "limit123"
        assert result["qty"] == 10
        assert result["limit_price"] == 149.5
        broker.client.submit_order.assert_called_once()
        call_arg = broker.client.submit_order.call_args.kwargs["order_data"]
        assert call_arg.symbol == "AAPL"
        assert call_arg.qty == 10
        assert call_arg.notional is None
        assert call_arg.limit_price == 149.5
        assert call_arg.extended_hours is True
        
    def test_submit_stop_order_with_qty(self):
        class FakeOrder:
            pass

        order_obj = FakeOrder()
        order_obj.id = "stop123"
        order_obj.symbol = "AAPL"
        order_obj.side = "sell"
        order_obj.qty = 10
        order_obj.stop_price = 160.0
        order_obj.time_in_force = "day"

        broker = AlpacaBrokerClient.__new__(AlpacaBrokerClient)
        broker._side_from_str = lambda x: x
        broker._tif_from_str = lambda x: x
        broker.client = MagicMock()
        broker.client.submit_order.return_value = order_obj

        result = broker.submit_stop_order(
            symbol="AAPL",
            side="sell",
            stop_price=160.0,
            qty=10,
            time_in_force="day",
        )

        assert isinstance(result, dict)
        assert result["id"] == "stop123"
        assert result["qty"] == 10
        assert result["stop_price"] == 160.0
        broker.client.submit_order.assert_called_once()
        call_arg = broker.client.submit_order.call_args.kwargs["order_data"]
        assert call_arg.symbol == "AAPL"
        assert call_arg.qty == 10
        assert call_arg.notional is None
        assert call_arg.stop_price == 160.0
        
    def test_submit_stop_limit_order_with_qty(self):
        class FakeOrder:
            pass

        order_obj = FakeOrder()
        order_obj.id = "stop_limit123"
        order_obj.symbol = "AAPL"
        order_obj.side = "sell"
        order_obj.qty = 10
        order_obj.stop_price = 160.0
        order_obj.limit_price = 159.5
        order_obj.time_in_force = "day"

        broker = AlpacaBrokerClient.__new__(AlpacaBrokerClient)
        broker._side_from_str = lambda x: x
        broker._tif_from_str = lambda x: x
        broker.client = MagicMock()
        broker.client.submit_order.return_value = order_obj

        result = broker.submit_stop_limit_order(
            symbol="AAPL",
            side="sell",
            stop_price=160.0,
            limit_price=159.5,
            qty=10,
            time_in_force="day",
        )

        assert isinstance(result, dict)
        assert result["id"] == "stop_limit123"
        assert result["qty"] == 10
        assert result["stop_price"] == 160.0
        assert result["limit_price"] == 159.5
        broker.client.submit_order.assert_called_once()
        call_arg = broker.client.submit_order.call_args.kwargs["order_data"]
        assert call_arg.symbol == "AAPL"
        assert call_arg.qty == 10
        assert call_arg.notional is None
        assert call_arg.stop_price == 160.0
        assert call_arg.limit_price == 159.5
        
    def test_submit_bracket_order_success(self):
        class FakeOrder:
            pass

        order_obj = FakeOrder()
        order_obj.id = "bracket123"
        order_obj.symbol = "AAPL"
        order_obj.side = "buy"
        order_obj.qty = 10
        order_obj.stop_loss_price = 145.0
        order_obj.take_profit_price = 160.0
        order_obj.time_in_force = "day"

        broker = AlpacaBrokerClient.__new__(AlpacaBrokerClient)
        broker._side_from_str = lambda x: x
        broker._tif_from_str = lambda x: x
        broker.client = MagicMock()
        broker.client.submit_order.return_value = order_obj

        result = broker.submit_bracket_order(
            symbol="AAPL",
            side="buy",
            qty=10,
            entry_type="market",
            entry_price=None,
            take_profit_price=160.0,
            stop_loss_price=145.0,
            time_in_force="day",
        )

        assert isinstance(result, dict)
        assert result["id"] == "bracket123"
        assert result["qty"] == 10
        assert result["take_profit_price"] == 160.0
        assert result["stop_loss_price"] == 145.0
        broker.client.submit_order.assert_called_once()

    def test_cancel_orders_success(self):
        broker = AlpacaBrokerClient.__new__(AlpacaBrokerClient)
        broker.client = MagicMock()
        broker.client.cancel_orders.return_value = [
            {"id": "order1"},
            {"id": "order2"},
        ]
        broker.client.cancel_order_by_id.return_value = MagicMock()

        result = broker.cancel_orders(order_ids=["order1", "order2"], cancel_all=False)

        assert isinstance(result, dict)
        assert result["total"] == 2
        assert result["success_count"] == 2
        assert result["failed_count"] == 0
        broker.client.cancel_order_by_id.assert_called()
        
    def test_get_equity_and_cash_success(self):
        class FakeAccount:
            pass

        account = FakeAccount()
        account.equity = "100000.0"
        account.cash = "50000.0"

        broker = AlpacaBrokerClient.__new__(AlpacaBrokerClient)
        broker.client = MagicMock()
        broker.client.get_account.return_value = account

        result = broker.get_equity_and_cash()

        assert isinstance(result, dict)
        assert result["equity"] == 100000.0
        assert result["cash"] == 50000.0
        
    def test_is_trading_blocked_success(self):
        class FakeAccount:
            pass

        account = FakeAccount()
        account.trading_blocked = True

        broker = AlpacaBrokerClient.__new__(AlpacaBrokerClient)
        broker.client = MagicMock()
        broker.client.get_account.return_value = account

        result = broker.is_trading_blocked()

        assert isinstance(result, bool)
        assert result is True
    
    def test_get_latest_trade_success(self):
        class FakeTrade:
            def __init__(self):
                self.price = 150.25
                self.size = 100
                self.exchange = "Q"
                self.conditions = ["R"]
                self.timestamp = datetime(2025, 5, 1, 12, 0, 0)
                self.id = "trade123"
                self.tape = "Q"

        from datetime import datetime

        broker = AlpacaBrokerClient.__new__(AlpacaBrokerClient)
        broker.data_client = MagicMock()
        broker.data_client.get_stock_latest_trade.return_value = {"AAPL": FakeTrade()}

        result = broker.get_latest_trade("AAPL")

        assert isinstance(result, dict)
        assert result["symbol"] == "AAPL"
        assert result["price"] == 150.25
        assert result["exchange"] == "Q"
    
    def test_get_latest_quote_success(self):
        class FakeQuote:
            def __init__(self):
                self.bid_price = 150.10
                self.bid_size = 200
                self.ask_price = 150.30
                self.ask_size = 150
                self.timestamp = datetime(2025, 5, 1, 12, 0, 0)
                self.conditions = ["R"]
                self.tape = "Q"

        from datetime import datetime

        broker = AlpacaBrokerClient.__new__(AlpacaBrokerClient)
        broker.data_client = MagicMock()
        broker.data_client.get_stock_latest_quote.return_value = {"AAPL": FakeQuote()}

        result = broker.get_latest_quote("AAPL")

        assert isinstance(result, dict)
        assert result["symbol"] == "AAPL"
        assert result["bid_price"] == 150.10
        assert result["ask_price"] == 150.30
        
    def test_get_portfolio_history_success(self):
        class FakeHistory:
            pass

        history = FakeHistory()
        history.timestamp = [1640995200, 1640998800, 1641002400]
        history.equity = [100000.0, 101000.0, 100500.0]

        broker = AlpacaBrokerClient.__new__(AlpacaBrokerClient)
        broker.client = MagicMock()
        broker.client.get_portfolio_history.return_value = history

        result = broker.get_portfolio_history()

        assert isinstance(result, dict)
        assert "historical" in result
        assert len(result["historical"]) == 3
        assert result["historical"][0]["date"].endswith("Z")
        assert result["historical"][0]["value"] == 100000.0
        broker.client.get_portfolio_history.assert_called_once()