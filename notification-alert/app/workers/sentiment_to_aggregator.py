import json
from redis.asyncio import Redis
from app.core.config import env_config


class SentimentAggregator:
    def __init__(self):
        self.r = Redis(
            host=env_config.redis_host,
            port=env_config.redis_port,
            password=env_config.redis_password,
            decode_responses=True,
        )
        self.sentiment_stream = env_config.redis_sentiment_stream
        self.aggregator_stream = env_config.redis_aggregator_stream

    async def async_start(self):
        print("🔄 Sentiment stream → aggregator stream")

        last_id = "0"

        while True:
            messages = await self.r.xread(
                streams={self.sentiment_stream: last_id},
                block=5000,
            )

            for _, events in messages:
                # print(events)
                for event_id, data in events:
                    ticker_meta_raw = data.get("ticker_metadata")
                    # print(data)
                    ticker_meta = json.loads(ticker_meta_raw)
                    print(ticker_meta)

                    for ticker, meta in ticker_meta.items():
                        print(meta)
                        event_proposal = meta.get("event_proposal") or {}
                        aggregator_data = {
                            "event_type": "NEWS_UPDATE",
                            "id": data.get("id"),
                            "ticker": ticker,
                            "event_type_meta": meta.get("event_type") or "",
                            "proposed_event_type": event_proposal.get("proposed_event_name") or "",
                            "proposed_event_category": event_proposal.get("event_category") or "",
                            "sentiment_score": meta.get("sentiment_score") or "",
                            "event_description": meta.get("event_description") or "",
                            "proposed_event_description": event_proposal.get("description") or "",
                            "sentiment_reasoning": meta.get("sentiment_reasoning") or ""
                        }
                        print(aggregator_data)

                        await self.r.xadd(
                            self.aggregator_stream,
                            aggregator_data,
                        )
                        print("🔁 News event:", aggregator_data)

                    last_id = event_id