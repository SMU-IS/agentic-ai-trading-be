import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock


def _run(coro):
    return asyncio.run(coro)


def _make_ws(fail=False):
    ws = MagicMock()
    ws.send_json = AsyncMock(side_effect=Exception("dead") if fail else None)
    return ws


class TestWSManager:

    @pytest.fixture(autouse=True)
    def _setup(self):
        from app.services.ws_manager import WSManager
        self.m = WSManager()

    # HAPPY PATH ---------------------------------------------------------------

    def test_happy_connect_adds_to_all_and_user_connections(self):
        """[HAPPY] connect adds websocket to both all_connections and user_connections."""
        ws = _make_ws()
        _run(self.m.connect(ws, "u1"))
        assert ws in self.m.all_connections
        assert ws in self.m.user_connections["u1"]

    def test_happy_connect_two_different_users(self):
        """[HAPPY] Two different users each get a separate entry in user_connections."""
        ws1, ws2 = _make_ws(), _make_ws()
        _run(self.m.connect(ws1, "u1"))
        _run(self.m.connect(ws2, "u2"))
        assert "u1" in self.m.user_connections
        assert "u2" in self.m.user_connections
        assert len(self.m.all_connections) == 2

    def test_happy_same_user_two_connections(self):
        """[HAPPY] Same user connecting twice has two entries; disconnect removes one."""
        ws1, ws2 = _make_ws(), _make_ws()
        _run(self.m.connect(ws1, "u1"))
        _run(self.m.connect(ws2, "u1"))
        assert len(self.m.user_connections["u1"]) == 2
        self.m.disconnect(ws1, "u1")
        assert "u1" in self.m.user_connections
        assert ws2 in self.m.user_connections["u1"]

    def test_happy_send_to_user_delivers_message(self):
        """[HAPPY] send_to_user sends message to all connections of the specified user."""
        ws = _make_ws()
        _run(self.m.connect(ws, "u1"))
        result = _run(self.m.send_to_user("u1", {"msg": "hello"}))
        assert result is True
        ws.send_json.assert_awaited_once_with({"msg": "hello"})

    def test_happy_broadcast_sends_to_all(self):
        """[HAPPY] broadcast delivers the message to every connected websocket."""
        ws1, ws2 = _make_ws(), _make_ws()
        _run(self.m.connect(ws1, "u1"))
        _run(self.m.connect(ws2, "u2"))
        result = _run(self.m.broadcast({"type": "PING"}))
        assert result is True
        ws1.send_json.assert_awaited_once()
        ws2.send_json.assert_awaited_once()

    def test_happy_disconnect_removes_from_all_and_user_connections(self):
        """[HAPPY] disconnect removes websocket from both stores; empty user entry is cleaned up."""
        ws = _make_ws()
        _run(self.m.connect(ws, "u1"))
        self.m.disconnect(ws, "u1")
        assert ws not in self.m.all_connections
        assert "u1" not in self.m.user_connections

    # BOUNDARY PATH ------------------------------------------------------------

    def test_boundary_send_to_user_unknown_returns_false(self):
        """[BOUNDARY] send_to_user for a non-existent user_id returns False immediately."""
        result = _run(self.m.send_to_user("nobody", {"msg": "hi"}))
        assert result is False

    def test_boundary_broadcast_no_connections_returns_true(self):
        """[BOUNDARY] broadcast with zero connections still returns True."""
        result = _run(self.m.broadcast({"type": "TEST"}))
        assert result is True

    def test_boundary_disconnect_unregistered_ws_is_safe(self):
        """[BOUNDARY] disconnect on a websocket that was never registered does not raise."""
        self.m.disconnect(_make_ws(), "ghost")  # must not raise

    # SAD PATH -----------------------------------------------------------------

    def test_sad_broadcast_dead_connection_removed_from_all_and_user(self):
        """[SAD] Failed send in broadcast prunes the dead connection from both stores."""
        good, bad = _make_ws(), _make_ws(fail=True)
        _run(self.m.connect(good, "u1"))
        _run(self.m.connect(bad, "u2"))
        result = _run(self.m.broadcast({"type": "TEST"}))
        assert result is True
        assert bad not in self.m.all_connections
        assert "u2" not in self.m.user_connections
        assert good in self.m.all_connections

    def test_sad_send_to_user_all_fail_returns_false(self):
        """[SAD] send_to_user where the connection raises on send returns False."""
        ws = _make_ws(fail=True)
        _run(self.m.connect(ws, "u1"))
        result = _run(self.m.send_to_user("u1", {"msg": "hi"}))
        assert result is False
