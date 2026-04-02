"""
Unit Tests — Health Check Endpoint
File: app/tests/test_health.py

Run from qdrant-retrieval/:
    pytest
"""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# ─── Happy path ───────────────────────────────────────────────────────────────

def test_healthcheck_healthy():
    """Redis ok and worker heartbeat found → status healthy."""
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    mock_redis.scan.return_value = (0, ["vectorisation:heartbeat:worker_abc123"])

    with patch("app.main.redis_client", mock_redis):
        response = client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Qdrant Retrieval Service is healthy"
    assert data["redis"] is True
    assert data["worker_alive"] is True
    assert data["total_active_workers"] == 1
    assert "worker_abc123" in data["active_workers"]


def test_healthcheck_multiple_workers():
    """Multiple active workers → all reported."""
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    mock_redis.scan.return_value = (
        0,
        [
            "vectorisation:heartbeat:worker_aaa",
            "vectorisation:heartbeat:worker_bbb",
        ],
    )

    with patch("app.main.redis_client", mock_redis):
        response = client.get("/")

    data = response.json()
    assert data["total_active_workers"] == 2
    assert "worker_aaa" in data["active_workers"]
    assert "worker_bbb" in data["active_workers"]


# ─── Sad path ─────────────────────────────────────────────────────────────────

def test_healthcheck_no_workers():
    """Redis ok but no heartbeat keys → worker_alive False."""
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    mock_redis.scan.return_value = (0, [])

    with patch("app.main.redis_client", mock_redis):
        response = client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert data["redis"] is True
    assert data["worker_alive"] is False
    assert data["total_active_workers"] == 0
    assert data["active_workers"] == []


def test_healthcheck_redis_down():
    """Redis ping raises → status unhealthy."""
    mock_redis = MagicMock()
    mock_redis.ping.side_effect = Exception("Connection refused")

    with patch("app.main.redis_client", mock_redis):
        response = client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["redis"] is False
    assert data["worker_alive"] is False


# ─── Edge cases ───────────────────────────────────────────────────────────────

def test_healthcheck_scan_multiple_pages():
    """scan returns non-zero cursor first → collects across pages."""
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    mock_redis.scan.side_effect = [
        (42, ["vectorisation:heartbeat:worker_page1"]),
        (0,  ["vectorisation:heartbeat:worker_page2"]),
    ]

    with patch("app.main.redis_client", mock_redis):
        response = client.get("/")

    data = response.json()
    assert data["total_active_workers"] == 2
    assert "worker_page1" in data["active_workers"]
    assert "worker_page2" in data["active_workers"]


def test_healthcheck_worker_id_extracted():
    """Worker ID stripped correctly from heartbeat key."""
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    mock_redis.scan.return_value = (0, ["vectorisation:heartbeat:a1b2c3"])

    with patch("app.main.redis_client", mock_redis):
        response = client.get("/")

    data = response.json()
    assert data["active_workers"] == ["a1b2c3"]
