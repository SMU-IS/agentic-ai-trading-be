import pytest
from unittest.mock import MagicMock, patch
from typing import List, Dict, Any
from fastapi.testclient import TestClient
from fastapi import status
from datetime import datetime

from app.api.routes.brokerage import router  # Adjust path if needed


@pytest.fixture
def client() -> TestClient:
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def mock_services_brokerage():
    """Mock services.brokerage with proper return types."""
    mock_broker = MagicMock()
    with patch('app.core.services.services.brokerage', mock_broker):
        yield mock_broker


@pytest.fixture
def mock_services_trading_db():
    """Mock trading_db for order enrichment."""
    mock_db = MagicMock()
    mock_db.get_reasonings_batch.return_value = {
        "order123": {
            "reasonings": "Test reasoning",
            "risk_evaluation": {"max_loss": 0.05},
            "risk_adjustments_made": ["reduced_qty"],
            "signal_data": {"confidence": 0.85}
        }
    }
    with patch('app.core.services.services.trading_db', mock_db):
        yield mock_db


class TestHealthAndDebug:
    def test_healthcheck(self, client: TestClient):
        response = client.get("/healthcheck")
        assert response.status_code == 200
        assert response.json() == {"status": "Alpacca service is healthy"}
    
    def test_debug_feed_sip_feed(self, client: TestClient, mock_services_brokerage):
        mock_services_brokerage.get_latest_quote.return_value = {
            "exchange": "Q",
            "bid_price": 150.10,
            "ask_price": 150.30,
        }

        response = client.get("/debug_feed")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["feed_used"] == "SIP"
        assert data["exchange"] == "Q"
        assert data["sample_quote"]["bid_price"] == 150.10

    def test_debug_feed_iex_feed(self, client: TestClient, mock_services_brokerage):
        mock_services_brokerage.get_latest_quote.return_value = {
            "exchange": "X",
            "bid_price": 150.10,
            "ask_price": 150.30,
        }

        response = client.get("/debug_feed")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["feed_used"] == "IEX"
        assert data["exchange"] == "X"


class TestAccountAndPositions:
    def test_get_account(self, client: TestClient, mock_services_brokerage):
        mock_services_brokerage.get_account.return_value = {
            "equity": "100000.00",
            "cash": "50000.00",
            "buying_power": "200000.00",
            "trading_blocked": False
        }
        response = client.get("/account")
        assert response.status_code == 200

    def test_get_positions(self, client: TestClient, mock_services_brokerage):
        # Mock returns LIST - fixes ResponseValidationError
        mock_services_brokerage.get_open_positions.return_value = []
        response = client.get("/positions")
        assert response.status_code == 200

    def test_get_position_exists(self, client: TestClient, mock_services_brokerage):
        mock_services_brokerage.get_position.return_value = {
            "symbol": "AAPL",
            "qty": 100,
            "avg_entry_price": 150.0
        }
        response = client.get("/positions/AAPL")
        assert response.status_code == 200


class TestOrdersListAndGet:
    def test_list_open_orders(self, client: TestClient, mock_services_brokerage):
        # Mock returns LIST - fixes ResponseValidationError
        mock_services_brokerage.list_open_orders.return_value = []
        response = client.get("/orders")
        assert response.status_code == 200

    def test_get_order(self, client: TestClient, mock_services_brokerage, mock_services_trading_db):
        # Mock returns DICT with expected structure
        mock_order = {
            "id": "order123",
            "symbol": "AAPL",
            "side": "buy",
            "qty": 10,
            "status": "filled"
        }
        mock_services_brokerage.get_order.return_value = mock_order
        response = client.get("/orders/order123")
        assert response.status_code == 200
        assert response.json()["trading_agent_reasonings"] == "Test reasoning"
    
    def test_list_all_orders_with_reasonings(self, client: TestClient, mock_services_brokerage, mock_services_trading_db):
        mock_orders = [
            {"id": 1, "symbol": "AAPL", "side": "buy", "qty": 10, "status": "filled"},
            {"id": 2, "symbol": "GOOGL", "side": "sell", "qty": 5, "status": "filled"},
        ]
        mock_services_brokerage.list_all_orders.return_value = mock_orders

        # Mock trading_db.get_reasonings_batch keyed by str(id)
        mock_services_trading_db.get_reasonings_batch.return_value = {
            "1": {
                "reasonings": "Test reasoning for AAPL",
                "risk_evaluation": {"max_loss": 0.05},
                "risk_adjustments_made": ["reduced_qty"],
                "signal_data": {"confidence": 0.85},
            },
            # "2" intentionally missing so no reasoning attached
        }

        response = client.get("/orders/all?limit=200")
        assert response.status_code == 200
        result = response.json()
        assert len(result) == 2

        # Order 1 has reasoning
        assert result[0]["id"] == 1
        assert result[0]["trading_agent_reasonings"] == "Test reasoning for AAPL"
        assert result[0]["is_trading_agent"] is True
        assert result[0]["risk_evaluation"]["max_loss"] == 0.05
        assert result[0]["risk_adjustments_made"] == ["reduced_qty"]
        assert result[0]["signal_data"] == {"confidence": 0.85}

        # Order 2 has no reasoning
        assert result[1]["id"] == 2
        assert result[1]["trading_agent_reasonings"] is None
        assert result[1]["is_trading_agent"] is False


class TestOrderCreation:
    def test_create_market_order(self, client: TestClient, mock_services_brokerage):
        mock_services_brokerage.submit_market_order.return_value = {
            "id": "market123",
            "status": "accepted"
        }
        body = {"symbol": "AAPL", "side": "buy", "qty": 10, "time_in_force": "day"}
        response = client.post("/orders/market", json=body)
        assert response.status_code == 201

    def test_create_bracket_order(self, client: TestClient, mock_services_brokerage):
        # Mock returns expected bracket structure
        mock_services_brokerage.submit_bracket_order.return_value = {
            "id": "bracket123",
            "status": "accepted"
        }
        body = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 10,
            "entry_type": "market",
            "entry_price": 150.0,
            "take_profit_price": 160.0,
            "stop_loss_price": 145.0,
            "time_in_force": "day"
        }
        response = client.post("/orders/bracket", json=body)
        assert response.status_code == 201
        assert response.json()["success"] is True
        
    def test_create_limit_order(self, client: TestClient, mock_services_brokerage):
        mock_services_brokerage.submit_limit_order.return_value = {
            "id": "limit123",
            "symbol": "AAPL",
            "side": "buy",
            "limit_price": 149.5,
            "qty": 10,
            "status": "accepted",
        }

        body = {
            "symbol": "AAPL",
            "side": "buy",
            "limit_price": 149.5,
            "qty": 10,
            "time_in_force": "day",
            "extended_hours": False,
        }
        response = client.post("/orders/limit", json=body)
        assert response.status_code == 201
        assert response.json()["id"] == "limit123"
        assert response.json()["limit_price"] == 149.5

    def test_create_stop_order(self, client: TestClient, mock_services_brokerage):
        mock_services_brokerage.submit_stop_order.return_value = {
            "id": "stop123",
            "symbol": "AAPL",
            "side": "sell",
            "stop_price": 160.0,
            "qty": 5,
            "status": "accepted",
        }

        body = {
            "symbol": "AAPL",
            "side": "sell",
            "stop_price": 160.0,
            "qty": 5,
            "time_in_force": "day",
        }
        response = client.post("/orders/stop", json=body)
        assert response.status_code == 201
        assert response.json()["id"] == "stop123"
        assert response.json()["stop_price"] == 160.0
    
    def test_create_stop_limit_order(self, client: TestClient, mock_services_brokerage):
        mock_services_brokerage.submit_stop_limit_order.return_value = {
            "id": "stop_limit123",
            "symbol": "AAPL",
            "side": "sell",
            "stop_price": 160.0,
            "limit_price": 159.5,
            "qty": 5,
            "status": "accepted",
        }

        body = {
            "symbol": "AAPL",
            "side": "sell",
            "stop_price": 160.0,
            "limit_price": 159.5,
            "qty": 5,
            "time_in_force": "day",
        }
        response = client.post("/orders/stop_limit", json=body)
        assert response.status_code == 201
        assert response.json()["id"] == "stop_limit123"
        assert response.json()["stop_price"] == 160.0
        assert response.json()["limit_price"] == 159.5
    
    def test_create_bracket_order_success(self, client: TestClient, mock_services_brokerage):
        # Mock the broker.return to match what submit_bracket_order actually returns
        mock_order = {
            "id": "bracket123",
            "symbol": "AAPL",
            "status": "accepted",
        }
        mock_services_brokerage.submit_bracket_order.return_value = mock_order

        body = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 10,
            "entry_type": "market",
            "entry_price": 150.0,
            "take_profit_price": 160.0,
            "stop_loss_price": 145.0,
            "time_in_force": "day",
        }
        response = client.post("/orders/bracket", json=body)
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["order_id"] == "bracket123"
        assert data["symbol"] == "AAPL"
        assert data["status"] == "accepted"
        assert data["order"]["id"] == "bracket123"

class TestPositionManagement:
    def test_close_position(self, client: TestClient, mock_services_brokerage):
        mock_services_brokerage.close_position.return_value = {"order_id": "close123"}
        body = {"percentage": 100}
        response = client.post("/positions/AAPL/close", json=body)
        assert response.status_code == 200

    def test_close_all_positions(self, client: TestClient, mock_services_brokerage):
        mock_services_brokerage.close_all_positions.return_value = []
        body = {"cancel_orders": True}
        response = client.post("/positions/close_all", json=body)
        assert response.status_code == 200
    
    def test_cancel_orders_by_ids(self, client: TestClient, mock_services_brokerage):
        mock_services_brokerage.cancel_orders.return_value = {
            "cancelled": ["order1", "order2"],
        }

        body = {"order_ids": ["order1", "order2"], "cancel_all": False}
        response = client.request("DELETE", "/orders/cancel", json=body)
        assert response.status_code == 200
        assert set(response.json()["cancelled"]) == {"order1", "order2"}

    def test_cancel_all_orders(self, client: TestClient, mock_services_brokerage):
        mock_services_brokerage.cancel_orders.return_value = {
            "cancelled": "all",
        }

        body = {"order_ids": None, "cancel_all": True}
        response = client.request("DELETE", "/orders/cancel", json=body)
        assert response.status_code == 200
        assert response.json()["cancelled"] == "all"
        
class TestMarketDataEndpoints:
    def test_get_latest_trade(self, client: TestClient, mock_services_brokerage):
        # FIX: Match exact LatestTradeResponse schema
        mock_trade = {
            "symbol": "AAPL",
            "price": 150.25,
            "size": 100,
            "exchange": "N",
            "conditions": ["L"],
            "timestamp": "2026-03-06T02:47:00Z",
            "id": "trade123",
            "tape": "Q"
        }
        mock_services_brokerage.get_latest_trade.return_value = mock_trade
        response = client.get("/latest_trade/AAPL")
        assert response.status_code == 200

    def test_get_latest_quote(self, client: TestClient, mock_services_brokerage):
        # FIX: Match exact LatestQuoteResponse schema
        mock_quote = {
            "symbol": "AAPL",
            "bid_price": 150.10,
            "bid_size": 200,
            "ask_price": 150.30,
            "ask_size": 150,
            "timestamp": "2026-03-06T02:47:00Z",
            "conditions": ["R"],
            "tape": "Q"
        }
        mock_services_brokerage.get_latest_quote.return_value = mock_quote
        response = client.get("/latest_quote/AAPL")
        assert response.status_code == 200


class TestConvenienceEndpoints:
    def test_equity_cash(self, client: TestClient, mock_services_brokerage):
        mock_services_brokerage.get_equity_and_cash.return_value = {
            "equity": 100000.0,
            "cash": 50000.0
        }
        response = client.get("/account/equity_cash")
        assert response.status_code == 200

    def test_trading_blocked(self, client: TestClient, mock_services_brokerage):
        mock_services_brokerage.is_trading_blocked.return_value = False
        response = client.get("/account/trading_blocked")
        assert response.status_code == 200

class TestConflicts:
    def test_check_conflicts_no_conflicts(self, client: TestClient, mock_services_brokerage):
        mock_services_brokerage.check_conflicting_positions.return_value = {
            "symbol": "AAPL",
            "intended_side": "buy",
            "intended_qty": 10,
            "has_conflicts": False,
            "actions": [],
        }

        body = {
            "symbol": "AAPL",
            "intended_side": "buy",
            "intended_qty": 10.0,
            "auto_resolve": False,
        }
        response = client.post("/orders/check-conflicts", json=body)
        assert response.status_code == 200
        assert response.json()["symbol"] == "AAPL"
        assert response.json()["has_conflicts"] is False
        
    def test_check_conflicts_with_conflicts(self, client: TestClient, mock_services_brokerage):
        mock_services_brokerage.check_conflicting_positions.return_value = {
            "symbol": "AAPL",
            "intended_side": "buy",
            "intended_qty": 10,
            "has_conflicts": True,
            "actions": ["close_position", "cancel_order"],
        }

        body = {
            "symbol": "AAPL",
            "intended_side": "buy",
            "intended_qty": 10.0,
            "auto_resolve": False,
        }
        response = client.post("/orders/check-conflicts", json=body)
        assert response.status_code == 200
        assert response.json()["has_conflicts"] is True
        assert "close_position" in response.json()["actions"]
        
    def test_resolve_conflicts_no_auto_resolve(self, client: TestClient, mock_services_brokerage):
        mock_services_brokerage.resolve_conflicts.return_value = {
            "symbol": "AAPL",
            "intended_side": "buy",
            "intended_qty": 10.0,
            "auto_resolve": False,
            "resolved": False,
            "actions_needed": ["close_position", "cancel_order"],
            "details": "Manual cleanup required",
        }

        body = {
            "symbol": "AAPL",
            "intended_side": "buy",
            "intended_qty": 10.0,
            "auto_resolve": False,
        }
        response = client.post("/orders/resolve-conflicts", json=body)
        assert response.status_code == 200
        assert response.json()["symbol"] == "AAPL"
        assert response.json()["auto_resolve"] is False
        assert response.json()["resolved"] is False


    def test_resolve_conflicts_with_auto_resolve(self, client: TestClient, mock_services_brokerage):
        mock_services_brokerage.resolve_conflicts.return_value = {
            "symbol": "AAPL",
            "intended_side": "buy",
            "intended_qty": 10.0,
            "auto_resolve": True,
            "resolved": True,
            "actions": ["close_position", "cancel_order"],
            "details": "All conflicts resolved",
        }

        body = {
            "symbol": "AAPL",
            "intended_side": "buy",
            "intended_qty": 10.0,
            "auto_resolve": True,
        }
        response = client.post("/orders/resolve-conflicts", json=body)
        assert response.status_code == 200
        assert response.json()["auto_resolve"] is True
        assert response.json()["resolved"] is True
        assert "close_position" in response.json()["actions"]

class TestPortfolioHistory:
    def test_get_portfolio_history_success(self, client: TestClient, mock_services_brokerage):
        # Mock PortfolioHistoryResponse-compatible data
        mock_data = {
            "historical": [
                {"date": "2025-05-01T00:00:00.000Z", "value": 30.52},
                {"date": "2025-05-02T00:00:00.000Z", "value": 31.10},
                {"date": "2025-05-03T00:00:00.000Z", "value": 30.80},
            ]
        }
        mock_services_brokerage.get_portfolio_history.return_value = mock_data

        response = client.get("/portfolio_history")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "historical" in data
        assert len(data["historical"]) == 3
        assert data["historical"][0]["date"] == "2025-05-01T00:00:00.000Z"
        assert data["historical"][0]["value"] == 30.52

    def test_get_portfolio_history_error(self, client: TestClient, mock_services_brokerage):
        mock_services_brokerage.get_portfolio_history.return_value = {
            "error": "Failed to fetch portfolio history"
        }

        response = client.get("/portfolio_history")
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Failed to fetch portfolio history" in response.json()["detail"]
    