"""
Scraper Controller — TradingView Service
==========================================
Class-based controller that orchestrates batch or stream ingestion.
Exposed as a singleton `scraper_controller` imported by main.py and the router.

MODE=batch  → Runs Minds + Ideas batch ingestion once in a background thread, then exits.
MODE=stream → Runs Minds + Ideas stream loops concurrently in background threads.
"""

import os
import logging
import threading

logger = logging.getLogger(__name__)


class ScraperController:

    def __init__(self):
        self._running = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    async def start(self, app) -> dict:
        if self._running:
            return {"status": "already_running"}

        mode = os.getenv("MODE", "batch").lower()
        self._stop_event.clear()
        self._running = True
        redis_client = app.state.redis_client

        if mode == "batch":
            self._thread = threading.Thread(
                target=self._run_batch,
                args=(redis_client,),
                name="tradingview-batch",
                daemon=True,
            )
        elif mode == "stream":
            self._thread = threading.Thread(
                target=self._run_stream,
                args=(redis_client,),
                name="tradingview-stream",
                daemon=True,
            )
        else:
            self._running = False
            raise ValueError(f"Unknown MODE '{mode}'. Use 'batch' or 'stream'.")

        self._thread.start()
        logger.info(f"[ScraperController] Started in '{mode}' mode")
        return {"status": "started", "mode": mode}

    async def stop(self, app) -> dict:
        if not self._running:
            return {"status": "not_running"}

        self._stop_event.set()
        self._running = False
        logger.info("[ScraperController] Stop signal sent")
        return {"status": "stopped"}

    def status(self) -> dict:
        return {
            "running": self._running,
            "thread": self._thread.name if self._thread else None,
            "alive": self._thread.is_alive() if self._thread else False,
        }

    def _run_batch(self, redis_client):
        from app.services.tradingview_minds_batch_ingestion import TradingViewMindsBatchIngestion
        from app.services.tradingview_ideas_batch_ingestion import TradingViewIdeasBatchIngestion

        try:
            logger.info("[ScraperController] Running Minds batch ingestion...")
            minds = TradingViewMindsBatchIngestion(redis_client)
            minds.run()

            logger.info("[ScraperController] Running Ideas batch ingestion...")
            ideas = TradingViewIdeasBatchIngestion(redis_client)
            ideas.run()

            logger.info("[ScraperController] Batch ingestion complete.")
        except Exception as e:
            logger.error(f"[ScraperController] Batch error: {e}", exc_info=True)
        finally:
            self._running = False

    def _run_stream(self, redis_client):
        from app.services.tradingview_minds_stream_ingestion import TradingViewMindsStreamIngestion
        from app.services.tradingview_ideas_stream_ingestion import TradingViewIdeasStreamIngestion

        minds = TradingViewMindsStreamIngestion(redis_client)
        ideas = TradingViewIdeasStreamIngestion(redis_client)

        minds_thread = threading.Thread(target=minds.run, name="minds-stream", daemon=True)
        ideas_thread = threading.Thread(target=ideas.run, name="ideas-stream", daemon=True)

        try:
            minds_thread.start()
            ideas_thread.start()

            # Block until stop signal received
            self._stop_event.wait()

            minds._running = False
            ideas._running = False

            minds_thread.join(timeout=10)
            ideas_thread.join(timeout=10)
        except Exception as e:
            logger.error(f"[ScraperController] Stream error: {e}", exc_info=True)
        finally:
            self._running = False


scraper_controller = ScraperController()
