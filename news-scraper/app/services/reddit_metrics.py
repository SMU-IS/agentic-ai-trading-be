from datetime import datetime
class RedditMetricsService:
    def __init__(self, redis_client):
        self.redis = redis_client

    def get_posts_last_day(self):
        now_ts = datetime.now().timestamp()
        self.redis.zremrangebyscore("newsscraper:metrics:posts_1d", 0, now_ts - 86400)
        return self.redis.zcard("newsscraper:metrics:posts_1d")

    def get_avg_latency_1d(self):
        now_ts = datetime.now().timestamp()
        self.redis.zremrangebyscore("newsscraper:metrics:latency_1d", 0, now_ts - 86400)

        post_ids = self.redis.zrange("newsscraper:metrics:latency_1d", 0, -1)
        if not post_ids:
            return 0

        latencies = [
            float(self.redis.hget("newsscraper:metrics:latency_values", pid))
            for pid in post_ids
        ]

        return sum(latencies) / len(latencies)
    
    def get_avg_latency(self):
        latency_sum = self.redis.get("newsscraper:metrics:latency_sum")
        latency_count = self.redis.get("newsscraper:metrics:latency_count")

        if not latency_sum or not latency_count:
            return 0

        return float(latency_sum) / int(latency_count)