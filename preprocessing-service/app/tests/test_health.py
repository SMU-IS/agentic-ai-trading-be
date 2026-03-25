"""
Unit Tests — Health Check Endpoint
File: app/tests/test_health.py

Run from preprocessing-service/:
    pytest
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# ─── Happy path ───────────────────────────────────────────────────────────────


def test_healthcheck_healthy():
    """Redis ok and worker heartbeat found → status healthy."""
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    mock_redis.scan.return_value = (0, ["preprocessing:heartbeat:worker_abc123"])

    with patch("app.main.redis_client", mock_redis):
        response = client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["redis"] is True
    assert data["worker_alive"] is True
    assert data["total_active_workers"] == 1
    assert "worker_abc123" in data["active_workers"]


def test_healthcheck_multiple_workers():
    """Multiple active workers → all reported in active_workers list."""
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    mock_redis.scan.return_value = (
        0,
        [
            "preprocessing:heartbeat:worker_aaa",
            "preprocessing:heartbeat:worker_bbb",
        ],
    )

    with patch("app.main.redis_client", mock_redis):
        response = client.get("/")

    data = response.json()
    assert data["status"] == "healthy"
    assert data["total_active_workers"] == 2
    assert "worker_aaa" in data["active_workers"]
    assert "worker_bbb" in data["active_workers"]


# ─── Sad path ─────────────────────────────────────────────────────────────────


def test_healthcheck_worker_unreachable():
    """Redis ok but no worker heartbeat keys → status worker_unreachable."""
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    mock_redis.scan.return_value = (0, [])

    with patch("app.main.redis_client", mock_redis):
        response = client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "worker_unreachable"
    assert data["redis"] is True
    assert data["worker_alive"] is False
    assert data["total_active_workers"] == 0
    assert data["active_workers"] == []


def test_healthcheck_redis_down():
    """Redis ping raises exception → status unhealthy."""
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


def test_healthcheck_scan_requires_multiple_iterations():
    """scan returns non-zero cursor first, then 0 → all keys collected across pages."""
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    mock_redis.scan.side_effect = [
        (42, ["preprocessing:heartbeat:worker_page1"]),  # cursor != 0, continue
        (0, ["preprocessing:heartbeat:worker_page2"]),  # cursor == 0, stop
    ]

    with patch("app.main.redis_client", mock_redis):
        response = client.get("/")

    data = response.json()
    assert data["total_active_workers"] == 2
    assert "worker_page1" in data["active_workers"]
    assert "worker_page2" in data["active_workers"]


def test_healthcheck_worker_id_extracted_from_key(service=None):
    """Worker ID is correctly stripped from the full heartbeat key name."""
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    mock_redis.scan.return_value = (
        0,
        ["preprocessing:heartbeat:a1b2c3"],
    )

    with patch("app.main.redis_client", mock_redis):
        response = client.get("/")

    data = response.json()
    # Only the ID portion after the last colon should appear
    assert data["active_workers"] == ["a1b2c3"]
