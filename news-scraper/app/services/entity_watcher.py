import time

class EntityWatcherService:
    def __init__(self, redis_client, hash_key):
        self.redis = redis_client
        self.hash_key = hash_key

    def run(self, poll_interval=5):

        print(f"[*] Watching hash '{self.hash_key}' for new entities...")

        processed_set = "entity_processed_set"

        while True:
            entities = self.redis.hgetall(self.hash_key)

            updated = False

            for ticker in entities:
                ticker = ticker.decode() if isinstance(ticker, bytes) else ticker
                if self.redis.sismember(processed_set, ticker):
                    continue

                print(f"[+] New entity detected: {ticker}")
                self.redis.lpush("batch_queue", ticker)
                self.redis.sadd(processed_set, ticker)
                updated = True

            if updated:
                self.redis.set("stream_version", time.time())

            time.sleep(poll_interval)
