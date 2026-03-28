"""
Tests for app/services/scraper_controller.py

Coverage:
  ScraperController.start()  — batch mode, stream mode, already running
  ScraperController.stop()   — running, not running
  ScraperController.status() — initial state, while running, after stop
"""

import asyncio
import os
from unittest.mock import MagicMock, patch

import fakeredis
import pytest

from app.services.scraper_controller import ScraperController


def _make_app():
    app = MagicMock()
    app.state.redis_client = fakeredis.FakeRedis(decode_responses=True)
    return app


class TestScraperController:

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.controller = ScraperController()
        self.app = _make_app()

    # HAPPY PATH ---------------------------------------------------------------

    def test_happy_start_batch_returns_started(self):
        """[HAPPY] start() in batch mode returns status=started and mode=batch."""
        with patch.dict(os.environ, {"MODE": "batch"}):
            with patch.object(self.controller, "_run_batch"):
                result = asyncio.run(self.controller.start(self.app))
        assert result["status"] == "started"
        assert result["mode"] == "batch"

    def test_happy_start_stream_returns_started(self):
        """[HAPPY] start() in stream mode returns status=started and mode=stream."""
        with patch.dict(os.environ, {"MODE": "stream"}):
            with patch.object(self.controller, "_run_stream"):
                result = asyncio.run(self.controller.start(self.app))
        assert result["status"] == "started"
        assert result["mode"] == "stream"

    def test_happy_start_sets_running_true(self):
        """[HAPPY] _running flag is True immediately after start()."""
        with patch.dict(os.environ, {"MODE": "batch"}):
            with patch.object(self.controller, "_run_batch"):
                asyncio.run(self.controller.start(self.app))
        assert self.controller._running is True

    def test_happy_stop_returns_stopped(self):
        """[HAPPY] stop() on a running controller returns status=stopped."""
        self.controller._running = True
        result = asyncio.run(self.controller.stop(self.app))
        assert result["status"] == "stopped"

    def test_happy_stop_clears_running_flag(self):
        """[HAPPY] _running is False after stop()."""
        self.controller._running = True
        asyncio.run(self.controller.stop(self.app))
        assert self.controller._running is False

    def test_happy_stop_sets_stop_event(self):
        """[HAPPY] stop() sets the _stop_event so stream threads can exit."""
        self.controller._running = True
        asyncio.run(self.controller.stop(self.app))
        assert self.controller._stop_event.is_set()

    def test_happy_status_while_running(self):
        """[HAPPY] status() reports running=True when scraper is active."""
        self.controller._running = True
        result = self.controller.status()
        assert result["running"] is True

    # BOUNDARY PATH ------------------------------------------------------------

    def test_boundary_status_default_is_not_running(self):
        """[BOUNDARY] Fresh controller reports running=False."""
        result = self.controller.status()
        assert result["running"] is False

    def test_boundary_status_has_required_keys(self):
        """[BOUNDARY] status() always returns running, thread, alive keys."""
        result = self.controller.status()
        assert "running" in result
        assert "thread" in result
        assert "alive" in result

    def test_boundary_status_thread_none_before_start(self):
        """[BOUNDARY] thread and alive are None/False before any start() call."""
        result = self.controller.status()
        assert result["thread"] is None
        assert result["alive"] is False

    # SAD PATH -----------------------------------------------------------------

    def test_sad_start_idempotent_when_already_running(self):
        """[SAD] Second start() call returns already_running, no new thread."""
        self.controller._running = True
        result = asyncio.run(self.controller.start(self.app))
        assert result["status"] == "already_running"

    def test_sad_stop_when_not_running(self):
        """[SAD] stop() when not running returns not_running."""
        result = asyncio.run(self.controller.stop(self.app))
        assert result["status"] == "not_running"

    def test_sad_invalid_mode_raises_value_error(self):
        """[SAD] Unknown MODE env var raises ValueError."""
        with patch.dict(os.environ, {"MODE": "invalid_mode"}):
            with pytest.raises(ValueError, match="Unknown MODE"):
                asyncio.run(self.controller.start(self.app))

    def test_sad_invalid_mode_does_not_set_running(self):
        """[SAD] ValueError from bad MODE leaves _running=False."""
        with patch.dict(os.environ, {"MODE": "invalid_mode"}):
            try:
                asyncio.run(self.controller.start(self.app))
            except ValueError:
                pass
        assert self.controller._running is False
