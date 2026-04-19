import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _run(coro):
    return asyncio.run(coro)


def _make_test_client():
    from app.services.notification_service import router
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestNotifyUsers:

    # HAPPY PATH ---------------------------------------------------------------

    def test_happy_news_received_calls_broadcast(self):
        """[HAPPY] NEWS_RECEIVED routes to ws_manager.broadcast with the full payload."""
        from app.services.notification_service import notify_users
        payload = {"type": "NEWS_RECEIVED", "id": "1"}
        with patch("app.services.notification_service.ws_manager") as mock_wm:
            mock_wm.broadcast = AsyncMock(return_value=True)
            result = _run(notify_users(payload))
        assert result is True
        mock_wm.broadcast.assert_awaited_once_with(payload)

    def test_happy_signal_generated_calls_broadcast(self):
        """[HAPPY] SIGNAL_GENERATED routes to ws_manager.broadcast."""
        from app.services.notification_service import notify_users
        with patch("app.services.notification_service.ws_manager") as mock_wm:
            mock_wm.broadcast = AsyncMock(return_value=True)
            result = _run(notify_users({"type": "SIGNAL_GENERATED", "signal_id": "s1"}))
        assert result is True
        mock_wm.broadcast.assert_awaited_once()

    def test_happy_trade_placed_sends_to_user(self):
        """[HAPPY] TRADE_PLACED routes to ws_manager.send_to_user with the given user_id."""
        from app.services.notification_service import notify_users
        payload = {"type": "TRADE_PLACED", "order": {}}
        with patch("app.services.notification_service.ws_manager") as mock_wm:
            mock_wm.send_to_user = AsyncMock(return_value=True)
            result = _run(notify_users(payload, user_id="user1"))
        assert result is True
        mock_wm.send_to_user.assert_awaited_once_with("user1", payload)

    # BOUNDARY PATH ------------------------------------------------------------

    def test_boundary_trade_placed_unknown_user_returns_false(self):
        """[BOUNDARY] TRADE_PLACED for an unconnected user_id returns False."""
        from app.services.notification_service import notify_users
        with patch("app.services.notification_service.ws_manager") as mock_wm:
            mock_wm.send_to_user = AsyncMock(return_value=False)
            result = _run(notify_users({"type": "TRADE_PLACED"}, user_id="nobody"))
        assert result is False

    # SAD PATH -----------------------------------------------------------------

    def test_sad_broadcast_dead_connections_returns_true(self):
        """[SAD] broadcast returns True even after pruning dead connections (ws_manager contract)."""
        from app.services.notification_service import notify_users
        with patch("app.services.notification_service.ws_manager") as mock_wm:
            mock_wm.broadcast = AsyncMock(return_value=True)
            result = _run(notify_users({"type": "NEWS_RECEIVED"}))
        assert result is True


class TestGetCurrentUser:

    def test_happy_header_present_returns_user_id(self):
        """[HAPPY] x-user-id header present → 200 with user_id in response."""
        client = _make_test_client()
        resp = client.get("/user", headers={"x-user-id": "alice"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["user_id"] == "alice"

    def test_sad_header_missing_returns_422(self):
        """[SAD] Missing x-user-id header → FastAPI returns 422 Unprocessable Entity."""
        client = _make_test_client()
        resp = client.get("/user")
        assert resp.status_code == 422


class TestWebSocketEndpoint:

    def test_happy_websocket_connects_and_disconnects(self):
        """[HAPPY] WebSocket with valid user_id connects and disconnects cleanly."""
        client = _make_test_client()
        with patch("app.services.notification_service.ws_manager") as mock_wm:
            mock_wm.connect = AsyncMock()
            mock_wm.disconnect = MagicMock()
            with client.websocket_connect("/ws/notifications?user_id=user42"):
                pass
        mock_wm.connect.assert_awaited_once()
        mock_wm.disconnect.assert_called_once()

    def test_sad_websocket_empty_user_id_skips_connect(self):
        """[SAD] Empty user_id → server closes with 4001 without calling ws_manager.connect."""
        client = _make_test_client()
        with patch("app.services.notification_service.ws_manager") as mock_wm:
            mock_wm.connect = AsyncMock()
            try:
                with client.websocket_connect("/ws/notifications?user_id="):
                    pass
            except Exception:
                pass
        mock_wm.connect.assert_not_awaited()

    def test_sad_websocket_cancelled_error_disconnects_user(self):
        """[SAD] asyncio.CancelledError during receive_text calls disconnect and re-raises."""
        from app.services.notification_service import websocket_endpoint
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.receive_text = AsyncMock(side_effect=asyncio.CancelledError())

        with patch("app.services.notification_service.ws_manager") as mock_wm:
            mock_wm.connect = AsyncMock()
            mock_wm.disconnect = MagicMock()
            with pytest.raises(asyncio.CancelledError):
                _run(websocket_endpoint(mock_ws, "user99"))

        mock_wm.disconnect.assert_called_once()
