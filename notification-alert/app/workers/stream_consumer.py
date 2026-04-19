import asyncio
import httpx
from redis.asyncio import Redis
from app.core.config import env_config
from app.services.notification_service import notify_users
from app.core.logger import logger

class StreamConsumer:
    def __init__(self):
        self.r = Redis(
            host=env_config.redis_host,
            port=env_config.redis_port,
            password=env_config.redis_password,
            decode_responses=True
        )

        self.streams = {
            env_config.redis_notification_stream: "news_notification_group",
            env_config.redis_analysis_stream: "analysis_notification_group",
            env_config.redis_trade_stream: "trade_notification_group"
        }
        self.consumer_name = "ws_consumer_1"

    async def create_groups(self):
        for stream_name, group_name in self.streams.items():
            try:
                await self.r.xgroup_create(
                    name=stream_name,
                    groupname=group_name,
                    id="$",
                    mkstream=True 
                )
                logger.info(f"✅ Created group {group_name} for {stream_name}")
            except Exception as e:
                if "BUSYGROUP" in str(e):
                    logger.info(f"ℹ️ Group {group_name} already exists")
                    await self.r.xgroup_setid(stream_name, group_name, "$")
                else:
                    raise 

    async def async_start(self):
        print("🔔 Notification service listening to streams...")
       
        await self.create_groups()

        while True:
            try:
                for stream_name, group_name in self.streams.items():
                    
                    messages = await self.r.xreadgroup(
                        groupname=group_name,
                        consumername=self.consumer_name,
                        streams={stream_name: ">"},
                        count=10,
                        block=5000
                    )

                    if not messages:
                        continue

                    for msg_stream, events in messages:
                        for event_id, data in events:

                            if isinstance(data, list):
                                data = dict(data)
                            try:
                                delivered = False
                                if stream_name == env_config.redis_notification_stream:
                                    # News notifications
                                    notification_payload = {
                                        "type": "NEWS_RECEIVED",
                                        "news_id": data.get("id"),
                                        "headline": data.get("headline"),
                                        "tickers": data.get("tickers"),
                                        "event_description": data.get("event_description")
                                    }
                                    delivered = await notify_users(notification_payload)


                                elif stream_name == env_config.redis_analysis_stream:
                                    # Signal notifications
                                    signal_id = data.get("signal_id")
                                    try:
                                        async with httpx.AsyncClient() as client:
                                            response = await client.get(
                                                f"{env_config.base_api}/trading/decisions/signals/{signal_id}"
                                            )
                                            
                                        full_signal = response.json()
                                        notification_payload = {
                                            "type": "SIGNAL_GENERATED",
                                            "signal_id": full_signal
                                        }
                                        delivered = await notify_users(notification_payload)

                                    except Exception:
                                        logger.exception(f"Failed processing signal {signal_id}")                                            

                                elif stream_name == env_config.redis_trade_stream:
                                    # Trade placed from agent-m notifications
                                    order_id = data.get("order_id")
                                    user_id = data.get('user_id')
                                    try:
                                        async with httpx.AsyncClient() as client:
                                            response = await client.get(
                                                f"{env_config.base_api}/trading/decisions/orders/{order_id}"
                                            )
                                            
                                        full_order = response.json()
                                        notification_payload = {
                                            "type": "TRADE_PLACED",
                                            "order": full_order
                                        }
                                        delivered = await notify_users(notification_payload, user_id = user_id)                                           

                                    except Exception:
                                        logger.exception(f"Failed processing signal {order_id}")

                                if delivered:
                                        logger.info("✅ Sent notification: %s", notification_payload)
                                else:
                                    logger.info("ℹ️ User offline, skipped: %s", notification_payload)    
                                await self.r.xack(msg_stream, group_name, event_id)                           


                            except Exception:
                                logger.exception(f"Failed processing {event_id} from {stream_name}")
                
            except asyncio.CancelledError:
                logger.info("🛑 StreamConsumer shutting...")
                raise
            except Exception:
                logger.exception("StreamConsumer error")
                await asyncio.sleep(2)