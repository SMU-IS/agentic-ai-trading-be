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

    def test_happy_start_sets_redis_running_flag(self):
        """[HAPPY] start() writes '1' to newsscraper:reddit:running in Redis."""
        fake_r = fakeredis.FakeRedis()
        app = self._make_app()
        app.state.redis_client = fake_r

        with patch.object(self.controller, "_run_stream"), \
             patch.object(self.controller, "_run_batch"):
            asyncio.run(self.controller.start(app))

        assert fake_r.get("newsscraper:reddit:running") == b"1"

    def test_happy_stop_sets_stop_event(self):
        """[HAPPY] stop() signals stop_event and sets _running=False."""
        app = self._make_app()
        self.controller._running = True
        self.controller._stop_event = threading.Event()
        self.controller._threads = []

        result = asyncio.run(self.controller.stop(app))

        assert result["message"] == "Scraper stopped"
        assert self.controller._running is False
        assert self.controller._stop_event.is_set()

    def test_happy_stop_sets_redis_flag_to_zero(self):
        """[HAPPY] stop() writes '0' to newsscraper:reddit:running in Redis."""
        fake_r = fakeredis.FakeRedis()
        fake_r.set("newsscraper:reddit:running", "1")
        app = self._make_app()
        app.state.redis_client = fake_r

        self.controller._running = True
        self.controller._stop_event = threading.Event()
        self.controller._threads = []

        asyncio.run(self.controller.stop(app))

        assert fake_r.get("newsscraper:reddit:running") == b"0"

    def test_happy_status_returns_running_state(self):
        """[HAPPY] status() reflects current _running=True flag."""
        self.controller._running = True
        assert self.controller.status() == {"running": True}

    # BOUNDARY PATH ------------------------------------------------------------

    def test_boundary_status_default_is_not_running(self):
        """[BOUNDARY] Fresh controller reports not running by default."""
        assert self.controller.status() == {"running": False}

    def test_boundary_stop_joins_alive_threads(self):
        """[BOUNDARY] stop() joins threads that are still alive."""
        app = self._make_app()
        self.controller._running = True
        self.controller._stop_event = threading.Event()

        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True
        self.controller._threads = [mock_thread]

        asyncio.run(self.controller.stop(app))

        mock_thread.join.assert_called_once_with(timeout=10)
        assert self.controller._threads == []

    def test_boundary_stop_skips_dead_threads(self):
        """[BOUNDARY] stop() skips join for threads that are no longer alive."""
        app = self._make_app()
        self.controller._running = True
        self.controller._stop_event = threading.Event()

        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = False
        self.controller._threads = [mock_thread]

        asyncio.run(self.controller.stop(app))

        mock_thread.join.assert_not_called()

    # SAD PATH -----------------------------------------------------------------

    def test_sad_start_idempotent_when_already_running(self):
        """[SAD] Calling start() when already running returns early."""
        self.controller._running = True
        result = asyncio.run(self.controller.start(MagicMock()))
        assert "already running" in result["message"]

    def test_sad_stop_when_not_running(self):
        """[SAD] Calling stop() when already stopped returns graceful message."""
        result = asyncio.run(self.controller.stop(MagicMock()))
        assert "already stopped" in result["message"]

    # INTERNAL METHOD tests ----------------------------------------------------

    def test_run_stream_creates_and_starts_service(self):
        """[UNIT] _run_stream instantiates RedditStreamService and calls run()."""
        self.controller._stop_event = threading.Event()

        with patch("app.services.scraper_controller.RedditStreamService") as MockStream:
            mock_svc = MockStream.return_value
            self.controller._run_stream(
                MagicMock(), MagicMock(), fakeredis.FakeRedis(), ["stocks"]
            )
            mock_svc.run.assert_called_once_with(["stocks"], self.controller._stop_event)

    def test_run_batch_creates_and_starts_service(self):
        """[UNIT] _run_batch instantiates RedditBatchService and calls run()."""
        with patch("app.services.scraper_controller.RedditBatchService") as MockBatch:
            mock_svc = MockBatch.return_value
            self.controller._run_batch(
                MagicMock(), MagicMock(), fakeredis.FakeRedis(), ["stocks"]
            )
            mock_svc.run.assert_called_once()
