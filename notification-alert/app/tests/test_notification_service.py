import json
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock


def _run(coro):
    return asyncio.run(coro)


def _make_ws(fail_on_send=False):
    ws = MagicMock()
    ws.send_text = AsyncMock(side_effect=Exception("disconnected") if fail_on_send else None)
    ws.accept = AsyncMock()
    ws.receive_text = AsyncMock()
    return ws


class TestNotifyUsers:

    @pytest.fixture(autouse=True)
    def _clear_connections(self):
        from app.services.notification_service import connections
        connections.clear()
        yield
        connections.clear()

    # HAPPY PATH ---------------------------------------------------------------

    def test_happy_single_connection_delivered(self):
        """[HAPPY] Message delivered to one client; returns True."""
        from app.services.notification_service import notify_users, connections
        ws = _make_ws()
        connections.append(ws)
        result = _run(notify_users({"type": "NEWS_RECEIVED", "id": "1"}))
        assert result is True
        ws.send_text.assert_awaited_once_with(
            json.dumps({"type": "NEWS_RECEIVED", "id": "1"})
        )

    def test_happy_multiple_connections_all_receive(self):
        """[HAPPY] All connected clients receive the same payload."""
        from app.services.notification_service import notify_users, connections
        ws1, ws2, ws3 = _make_ws(), _make_ws(), _make_ws()
        connections.extend([ws1, ws2, ws3])
        assert _run(notify_users({"type": "PING"})) is True
        for ws in [ws1, ws2, ws3]:
            ws.send_text.assert_awaited_once()

    def test_happy_payload_serialised_as_json(self):
        """[HAPPY] Non-ASCII payload survives JSON serialisation round-trip."""
        from app.services.notification_service import notify_users, connections
        ws = _make_ws()
        connections.append(ws)
        payload = {"type": "NEWS_RECEIVED", "headline": "日本語"}
        _run(notify_users(payload))
        assert json.loads(ws.send_text.call_args[0][0]) == payload

    # BOUNDARY PATH ------------------------------------------------------------

    def test_boundary_no_connections_returns_false(self):
        """[BOUNDARY] Empty connections list → returns False immediately."""
        from app.services.notification_service import notify_users
        assert _run(notify_users({"type": "TEST"})) is False

    # SAD PATH -----------------------------------------------------------------

    def test_sad_failed_connection_removed_good_one_kept(self):
        """[SAD] Dead WebSocket is pruned; healthy client stays in connections."""
        from app.services.notification_service import notify_users, connections
        good = _make_ws()
        bad = _make_ws(fail_on_send=True)
        connections.extend([good, bad])
        result = _run(notify_users({"type": "TEST"}))
        assert result is True
        assert bad not in connections
        assert good in connections

    def test_sad_all_connections_failed_returns_false(self):
        """[SAD] All sends raise → returns False; connections emptied."""
        from app.services.notification_service import notify_users, connections
        connections.extend([_make_ws(fail_on_send=True), _make_ws(fail_on_send=True)])
        result = _run(notify_users({"type": "TEST"}))
        assert result is False
        assert len(connections) == 0

