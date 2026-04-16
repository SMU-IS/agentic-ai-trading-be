import asyncio
import json

from redis.asyncio import Redis

from app.core.config import env_config
from app.core.logger import logger


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

        last_id = "$"

        while True:
            try:
                messages = await self.r.xread(
                    streams={self.sentiment_stream: last_id},
                    block=5000,
                )
            except Exception as e:
                logger.error(f"xread failed: {e}")
                await asyncio.sleep(5)
                continue

            for _, events in messages:
                for event_id, data in events:
                    last_id = event_id
                    ticker_meta_raw = data.get("ticker_metadata")

                    ticker_meta = json.loads(ticker_meta_raw.strip('"'))

                    tickers_info = []
                    for ticker, meta in ticker_meta.items():
                        tickers_info.append(
                            {
                                "symbol": ticker,
                                "event_type": meta.get("event_type") or "",
                                "sentiment_label": meta.get("sentiment_label") or "",
                            }
                        )

                    notification_data = {
                        "id": (data.get("id") or "").strip('"'),
                        "headline": json.loads(data.get("content") or "{}").get(
                            "title", ""
                        ),
                        "body": json.loads(data.get("content") or "{}").get("body", ""),
                        "tickers": json.dumps(tickers_info),
                        "event_description": "; ".join(
                            [
                                meta.get("event_description") or ""
                                for meta in ticker_meta.values()
                            ]
                        ),
                    }

                    await self.r.xadd(
                        self.notification_stream,
                        notification_data,
                    )
                    print("🔁 News event:", notification_data)


if __name__ == "__main__":
    import asyncio
    worker = SentimentBridge()
    asyncio.run(worker.async_start())
