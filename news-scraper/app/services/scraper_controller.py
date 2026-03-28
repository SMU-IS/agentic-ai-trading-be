import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.services.reddit_batch_ingestion import RedditBatchService
from app.services.reddit_stream_ingestion import RedditStreamService
from app.services.entity_watcher import EntityWatcherService


class ScraperController:
    def __init__(self):
        self._running = False
        self._threads = []
        self._stop_event = None
        
    async def start(self, app):
        if self._running:
            return {"message": "Scraper already running"}

        self._running = True
        self._stop_event = threading.Event() 

        reddit = app.state.reddit
        storage = app.state.storage
        redis_client = app.state.redis_client
        base_subreddits = app.state.base_subreddits

        redis_client.set("newsscraper:reddit:running", "1")

        stream_thread = threading.Thread(
            target=self._run_stream,
            args=(reddit, storage, redis_client, base_subreddits),
            daemon=True,
        )

        batch_thread = threading.Thread(
            target=self._run_batch,
            args=(reddit, storage, redis_client, base_subreddits),
            daemon=True,
        )

        # watcher_thread = threading.Thread(
        #     target=self._run_watcher,
        #     args=(redis_client,),
        #     daemon=True,
        # )

        # self._threads = [stream_thread, batch_thread, watcher_thread]

        self._threads = [stream_thread]
        for t in self._threads:
            t.start()

        return {"message": "Scraper started"}

    def _run_stream(self, reddit, storage, redis_client, base_subreddits):
        service = RedditStreamService(reddit, storage, redis_client)
        service.run(base_subreddits, self._stop_event)

    def _run_batch(self, reddit, storage, redis_client, base_subreddits):
        service = RedditBatchService(reddit, storage, redis_client)
        # service.run_worker(self._stop_event)
        service.run(base_subreddits)     

    # def _run_watcher(self, redis_client):
    #     service = EntityWatcherService(redis_client, "all_identified_tickers")

    #     while not self._stop_event.is_set():
    #         service.run()

    async def stop(self, app):
        if not self._running:
            return {"message": "Scraper already stopped"}

        redis_client = app.state.redis_client

        self._running = False
        redis_client.set("newsscraper:reddit:running", "0")
        self._stop_event.set()

        for t in self._threads:
            if t.is_alive():
                t.join(timeout=10)

        self._threads = []

        return {"message": "Scraper stopped"}

    def status(self):
        return {"running": self._running}


scraper_controller = ScraperController()