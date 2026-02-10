import json
from redis.asyncio import Redis
from app.core.config import env_config


class SentimentBridge:
    def __init__(self):
        self.r = Redis(
            host=env_config.redis_host,
            port=env_config.redis_port,
            password=env_config.redis_password,
            decode_responses=True,
        )
        self.sentiment_stream = env_config.redis_sentiment_stream
        self.notification_stream = env_config.redis_notification_stream

    async def async_start(self):
        print("🔄 Sentiment stream → notification stream")

        last_id = "0"

        while True:
            messages = await self.r.xread(
                streams={self.sentiment_stream: last_id},
                block=5000,
            )

            for _, events in messages:
                for event_id, data in events:
                    ticker_meta_raw = data.get("ticker_metadata")

                    ticker_meta = json.loads(ticker_meta_raw.strip('"'))

                    for ticker, meta in ticker_meta.items():
                        notification_data = {
                            "event_type": "NEWS_UPDATE",
                            "id": data.get("id").strip('"') if data.get("id") else None,
                            "ticker": ticker,
                            "event_type_meta": meta.get("event_type"),
                            "sentiment_score": meta.get("sentiment_score"),
                            "sentiment_confidence": meta.get("sentiment_confidence"),
                        }

                        await self.r.xadd(
                            self.notification_stream,
                            notification_data,
                        )
                        print("🔁 News event:", notification_data)

                    last_id = event_id
