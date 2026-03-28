import json
from redis.asyncio import Redis
from app.core.config import env_config
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


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
        self.group_name = "aggregator_notification_group"
        self.consumer_name = "ws_consumer_1"

    async def create_group(self):
        try:
            await self.r.xgroup_create(
                name=self.sentiment_stream,
                groupname=self.group_name,
                id="0",
                mkstream=True,
            )
            print(f"✅ Created group {self.group_name}")
        except Exception as e:
            if "BUSYGROUP" in str(e):
                print(f"ℹ️ Group {self.group_name} already exists")
            else:
                raise

    async def async_start(self):
        print("🔄 Sentiment stream → aggregator stream")
        await self.create_group()
        POST_TIMESTAMP = "post_timestamps"  

        while True:
            messages = await self.r.xreadgroup(
                groupname=self.group_name,
                consumername=self.consumer_name,
                streams={self.sentiment_stream: ">"},
                count=10,
                block=5000
            )

            if not messages:
                pending_messages = await self.r.xpending_range(
                    self.sentiment_stream,
                    self.group_name,
                    min="-",
                    max="+",
                    count=10,
                    consumername=self.consumer_name
                )
                if pending_messages:
                    message_ids = [msg["message_id"] for msg in pending_messages]
                    claimed = await self.r.xclaim(
                        self.sentiment_stream,
                        self.group_name,
                        self.consumer_name,
                        min_idle_time=0,
                        message_ids=message_ids
                    )

                    if claimed:
                        messages = [(self.sentiment_stream, claimed)]
                    else:
                        messages = []            

            if not messages:
                continue

            for _, events in messages:
                for event_id, data in events:
                    try:
                        ticker_meta_raw = data.get("ticker_metadata")
                        ticker_meta = json.loads(ticker_meta_raw)   
                        
                        sg_time = (
                                datetime
                                .fromtimestamp(int(event_id.split("-")[0]) / 1000, tz=timezone.utc)
                                .astimezone(ZoneInfo("Asia/Singapore"))
                            )

                        post_id = data.get("id")
                        post_id = post_id.strip('"')
                        await self.r.hset(
                            f"{POST_TIMESTAMP}:{post_id}",
                            "vectorised_timestamp",        
                            sg_time.isoformat()           
                        )
                        print(f"⏱️ Post {post_id}: Timestamped at Vectorisation Stage → {sg_time}")                                                   

                        for ticker, meta in ticker_meta.items():
                            aggregator_data = {
                                "event_type": "NEWS_UPDATE",
                                "id": data.get("id"),
                                "ticker": ticker,
                                "event_type_meta": meta.get("event_type") or "",
                                "sentiment_score": meta.get("sentiment_score") or 0.0,
                                "event_description": meta.get("event_description") or "",
                                "sentiment_reasoning": meta.get("sentiment_reasoning") or ""
                            }

                            await self.r.xadd(
                                self.aggregator_stream,
                                aggregator_data,
                            )
                            print("🔁 News event:", aggregator_data)

                        await self.r.xack(self.sentiment_stream, self.group_name, event_id)
                        print(f"✅ Acked {event_id}")                        

                    except Exception as e:
                        import traceback
                        print(f"❌ Error on {event_id}: {e}")
                        traceback.print_exc()