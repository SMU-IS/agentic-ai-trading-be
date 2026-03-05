import asyncio
import threading
from unittest.mock import MagicMock, patch
import pytest
import fakeredis


class TestScraperController:

    @pytest.fixture(autouse=True)
    def _setup(self):
        from app.services.scraper_controller import ScraperController
        self.controller = ScraperController()

    def _make_app(self):
        app = MagicMock()
        app.state.reddit = MagicMock()
        app.state.storage = MagicMock()
        app.state.redis_client = fakeredis.FakeRedis()
        app.state.base_subreddits = ["stocks"]
        return app

    # HAPPY PATH ---------------------------------------------------------------

    def test_happy_start_launches_scraper(self):
        """[HAPPY] start() returns started message and sets _running=True."""
        with patch.object(self.controller, "_run_stream"), \
             patch.object(self.controller, "_run_batch"):
            result = asyncio.run(self.controller.start(self._make_app()))

        assert result["message"] == "Scraper started"
        assert self.controller._running is True

    def test_happy_stop_sets_stop_event(self):
        """[HAPPY] stop() signals stop_event, sets _running=False."""
        self.controller._running = True
        self.controller._stop_event = threading.Event()
        self.controller._threads = []

        result = asyncio.run(self.controller.stop())

        assert result["message"] == "Scraper stopped"
        assert self.controller._running is False
        assert self.controller._stop_event.is_set()

    def test_happy_status_returns_running_state(self):
        """[HAPPY] status() reflects current _running=True flag."""
        self.controller._running = True
        assert self.controller.status() == {"running": True}

    # BOUNDARY PATH ------------------------------------------------------------

    def test_boundary_status_default_is_not_running(self):
        """[BOUNDARY] Fresh controller reports not running by default."""
        assert self.controller.status() == {"running": False}

    # SAD PATH -----------------------------------------------------------------

    def test_sad_start_idempotent_when_already_running(self):
        """[SAD] Calling start() when already running returns early."""
        self.controller._running = True
        result = asyncio.run(self.controller.start(MagicMock()))
        assert "already running" in result["message"]

    def test_sad_stop_when_not_running(self):
        """[SAD] Calling stop() when already stopped returns graceful message."""
        result = asyncio.run(self.controller.stop())
        assert "already stopped" in result["message"]
