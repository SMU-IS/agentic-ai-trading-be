import asyncio
from redis.asyncio import Redis
from app.core.config import env_config
from app.services.notification_service import notify_users

class StreamConsumer:
    def __init__(self):
        self.r = Redis(
            host=env_config.redis_host,
            port=env_config.redis_port,
            password=env_config.redis_password,
            decode_responses=True
        )

        self.notification_stream = env_config.redis_notification_stream
        self.analysis_stream = env_config.redis_analysis_stream
        self.last_ids = {
            self.notification_stream: "0",
            self.analysis_stream: "0"
        }

    async def async_start(self):
        print("🔔 Notification service listening to streams...")

        while True:
            try:
                streams_to_read = {
                    self.notification_stream: self.last_ids[self.notification_stream],
                    self.analysis_stream: self.last_ids[self.analysis_stream]
                }

                messages = await self.r.xread(streams=streams_to_read, block=5000)

                if not messages:
                    continue

                for stream_name, events in messages:
                    for event_id, data in events:
                        try:
                            if stream_name == self.notification_stream:
                                # News notifications
                                notification_payload = {
                                    "type": "NEWS_RECEIVED",
                                    "news_id": data.get("id"),
                                    "headline": data.get("headline"),
                                    "tickers": data.get("tickers"),
                                    "event_description": data.get("event_description")
                                }
                                await notify_users(notification_payload)
                                print("✅ Sent news notification:", notification_payload)

                            elif stream_name == self.analysis_stream:
                                # Trade / signal notifications
                                notification_payload = {
                                    "type": "SIGNAL_GENERATED",
                                    "signal_id": data.get("signal_id")
                                }
                                await notify_users(notification_payload)
                                print("✅ Sent signal notification:", notification_payload)

                            self.last_ids[stream_name] = event_id

                        except Exception as e:
                            print(f"Failed processing {event_id} from {stream_name}: {e}")

            except Exception as e:
                print(f"StreamConsumer error: {e}")
                await asyncio.sleep(2)