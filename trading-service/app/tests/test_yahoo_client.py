import pytest
from unittest.mock import MagicMock, patch, ANY
from typing import List, Dict, Any
from fastapi.testclient import TestClient
from fastapi import status
from datetime import datetime

from app.api.routes.yahoo import router
from app.core.yahoo_client import YahooClient


@pytest.fixture
def client() -> TestClient:
    """Create FastAPI test client."""
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def mock_yahoo_client() -> MagicMock:
    """Mock YahooClient."""
    mock_client = MagicMock(spec=YahooClient)
    return mock_client


@pytest.fixture
def mock_get_yahoo_client():
    """Mock get_yahoo_client dependency."""
    with patch('app.api.routes.yahoo.get_yahoo_client', return_value=MagicMock(spec=YahooClient)) as mock:
        yield mock


@pytest.fixture
def sample_quotes_data() -> Dict[str, List[Dict[str, Any]]]:
    """Sample quotes response data."""
    return {
        "AAPL": [
            {
                "timestamp": 1735689600,
                "open": 150.0,
                "high": 152.5,
                "low": 149.2,
                "close": 151.8,
                "volume": 12345678
            }
        ],
        "MSFT": [
            {
                "timestamp": 1735689600,
                "open": 280.0,
                "high": 282.1,
                "low": 278.5,
                "close": 281.2,
                "volume": 8765432
            }
        ]
    }


@pytest.fixture
def sample_history_data() -> Dict[str, Any]:
    """Sample history response data."""
    return {
        "symbol": "AAPL",
        "interval": "1d",
        "count": 5,
        "bars": [
            {"date": "2026-03-01", "close": 150.0, "volume": 1000000},
            {"date": "2026-03-02", "close": 152.0, "volume": 1100000},
        ]
    }


@pytest.fixture
def sample_latest_data() -> Dict[str, Any]:
    """Sample latest info response data."""
    return {
        "symbol": "AAPL",
        "timestamp": 1735689600.0,
        "price": {"last": 258.27, "previous_close": 261.00},
        "intraday": {"open": 260.0, "high": 261.5, "low": 257.8, "close": 258.27},
        "averages": {"sma_50": 255.3, "sma_200": 240.1},
        "fundamentals": {"market_cap": 4000000000000, "pe_ratio": 32.5},
        "change": {"day_pct": -1.25, "day_abs": -2.73}
    }


class TestQuotesEndpoint:
    """Test /quotes endpoint."""

    def test_get_quotes_multiple_symbols(self, client: TestClient, mock_get_yahoo_client, sample_quotes_data: Dict[str, List[Dict[str, Any]]]):
        """Test quotes for multiple symbols."""
        mock_client = mock_get_yahoo_client.return_value
        mock_client.get_quotes.return_value = sample_quotes_data

        response = client.get("/quotes?symbol=AAPL&symbol=MSFT")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["data"]["AAPL"][0]["close"] == 151.8
        assert data["data"]["MSFT"][0]["close"] == 281.2
        mock_client.get_quotes.assert_called_once_with(["AAPL", "MSFT"])

    def test_get_quotes_single_symbol(self, client: TestClient, mock_get_yahoo_client):
        """Test quotes for single symbol."""
        mock_client = mock_get_yahoo_client.return_value
        mock_client.get_quotes.return_value = {"AAPL": []}

        response = client.get("/quotes?symbol=AAPL")
        
        assert response.status_code == status.HTTP_200_OK
        mock_client.get_quotes.assert_called_once_with(["AAPL"])

    def test_get_quotes_no_symbols(self, client: TestClient, mock_get_yahoo_client):
        """Test quotes with no symbols (should handle gracefully)."""
        mock_client = mock_get_yahoo_client.return_value
        mock_client.get_quotes.return_value = {}

        response = client.get("/quotes")
        
        assert response.status_code == status.HTTP_200_OK
        mock_client.get_quotes.assert_called_once_with(None)

    def test_get_quotes_error(self, client: TestClient, mock_get_yahoo_client):
        """Test quotes endpoint error handling."""
        mock_get_yahoo_client.return_value.get_quotes.side_effect = Exception("Yahoo API error")

        response = client.get("/quotes?symbol=AAPL")
        
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Yahoo API error" in response.json()["detail"]


class TestHistoryEndpoint:
    """Test /history/{symbol} endpoint."""

    def test_get_history_with_period(self, client: TestClient, mock_get_yahoo_client, sample_history_data: Dict[str, Any]):
        """Test history with period parameter."""
        mock_client = mock_get_yahoo_client.return_value
        mock_client.get_history.return_value = sample_history_data

        response = client.get("/history/AAPL?interval=1d&period=1mo")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["symbol"] == "AAPL"
        assert data["count"] == 5
        mock_client.get_history.assert_called_once_with(
            symbol="AAPL", interval="1d", period="1mo", start=None, end=None
        )

    def test_get_history_with_start_end(self, client: TestClient, mock_get_yahoo_client, sample_history_data: Dict[str, Any]):
        """Test history with start/end dates."""
        mock_client = mock_get_yahoo_client.return_value
        mock_client.get_history.return_value = sample_history_data

        start_date = datetime(2026, 3, 1)
        response = client.get(f"/history/AAPL?interval=1d&start={start_date.isoformat()}")
        
        assert response.status_code == status.HTTP_200_OK
        mock_client.get_history.assert_called_once_with(
            symbol="AAPL", interval="1d", period=None, 
            start=ANY, end=None  # ANY matches datetime objects
        )

    def test_get_history_missing_period_or_start(self, client: TestClient):
        """Test validation error when no period or start provided."""
        response = client.get("/history/AAPL")
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Provide either period or start" in response.json()["detail"]

    def test_get_history_error(self, client: TestClient, mock_get_yahoo_client):
        """Test history endpoint error handling."""
        mock_get_yahoo_client.return_value.get_history.side_effect = Exception("History fetch failed")

        response = client.get("/history/AAPL?period=1mo")
        
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestLatestInfoEndpoint:
    """Test /latest/{symbol} endpoint."""

    def test_get_latest_info_success(self, client: TestClient, mock_get_yahoo_client, sample_latest_data: Dict[str, Any]):
        """Test successful latest info retrieval."""
        mock_client = mock_get_yahoo_client.return_value
        mock_client.get_latest_info.return_value = sample_latest_data

        response = client.get("/latest/AAPL")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["symbol"] == "AAPL"
        assert data["price"]["last"] == 258.27
        assert data["change"]["day_pct"] == -1.25
        mock_client.get_latest_info.assert_called_once_with("AAPL")

    def test_get_latest_info_error(self, client: TestClient, mock_get_yahoo_client):
        """Test latest info error handling."""
        mock_get_yahoo_client.return_value.get_latest_info.side_effect = Exception("Latest data unavailable")

        response = client.get("/latest/AAPL")
        
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Latest data unavailable" in response.json()["detail"]