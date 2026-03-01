import asyncio
import json
import signal
import uuid
import redis.asyncio as redis
from app.utils.logger import setup_logging
from app.core.config import env_config
from app.services._05_sentiment import LLMSentimentService
from app.scripts.storage import RedisStreamStorage

logger = setup_logging()

# ================= CONFIG =================
EVENT_STREAM_NAME = env_config.redis_event_stream
SENTIMENT_STREAM_NAME = env_config.redis_sentiment_stream

CONSUMER_GROUP = "sentiment_analysis_group"
CONSUMER_NAME = f"sentiment_analysis_{uuid.uuid4().hex[:6]}"

HEARTBEAT_KEY = f"sentiment_analysis:heartbeat:{CONSUMER_NAME}"
HEARTBEAT_INTERVAL = 30
HEARTBEAT_TTL = HEARTBEAT_INTERVAL * 3

BATCH_SIZE = 10
RECOVER_BATCH_SIZE = 100
MIN_IDLE_MS = 5000
CLEANUP_INTERVAL = 300


# ================= INIT =================
redis_client = redis.Redis(
    host=env_config.redis_host,
    port=int(env_config.redis_port),
    password=env_config.redis_password,
    decode_responses=True,
)

event_stream = RedisStreamStorage(EVENT_STREAM_NAME, redis_client)
sentiment_stream = RedisStreamStorage(SENTIMENT_STREAM_NAME, redis_client)

sentiment_service = LLMSentimentService()


# ==========================================================
# GROUP SETUP
# ==========================================================
async def setup_consumer_group():
    try:
        await event_stream.create_consumer_group(
            CONSUMER_GROUP,
            start_id="0",
            mkstream=True,
        )
        logger.info(f"✅ Consumer group {CONSUMER_GROUP} ready")
    except Exception:
        logger.warning("Group likely already exists")


async def finalize_message(msg_id: str):
    await event_stream.acknowledge(CONSUMER_GROUP, msg_id)
    await event_stream.delete(msg_id)


# ==========================================================
# HEARTBEAT
# ==========================================================
async def send_heartbeat():
    try:
        while True:
            await redis_client.set(
                HEARTBEAT_KEY,
                "alive",
                ex=HEARTBEAT_TTL,
            )
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    except asyncio.CancelledError:
        logger.warning("🛑 Heartbeat stopped")
        raise


# ==========================================================
# DECODE
# ==========================================================
def decode_message(data: dict):
    raw = data.get("data")

    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error(f"❌ Failed to decode JSON: {e}")
            return None

    return raw if isinstance(raw, dict) else data


# ==========================================================
# MESSAGE PROCESSING
# ==========================================================
async def process_message(msg_id: str, data: dict):
    decoded = decode_message(data)
    if not decoded:
        await finalize_message(msg_id)
        return

    sentiment_result = await sentiment_service.analyse(decoded)

    if not sentiment_result:
        await finalize_message(msg_id)
        return

    post_id = sentiment_result.get("id")

    try:
        await sentiment_stream.save(sentiment_result)
    except asyncio.CancelledError:
        raise

    await finalize_message(msg_id)

    logger.info(f"✅ Processed Post {post_id}")


# ==========================================================
# RECOVERY
# ==========================================================
async def recover_pending_messages():
    claimed = await event_stream.claim_pending(
        group_name=CONSUMER_GROUP,
        consumer_name=CONSUMER_NAME,
        min_idle_time_ms=MIN_IDLE_MS,
        count=RECOVER_BATCH_SIZE,
    )

    if not claimed:
        return

    logger.info(f"⚡ Recovered {len(claimed)} messages")

    for msg_id, data in claimed:
        try:
            await process_message(msg_id, data)
        except Exception as e:
            logger.error(f"❌ Recovery failed {msg_id}: {e}")


# ==========================================================
# CLEANUP
# ==========================================================
async def cleanup_dead_consumers():
    try:
        consumers = await redis_client.xinfo_consumers(
            EVENT_STREAM_NAME,
            CONSUMER_GROUP,
        )

        TEN_MIN_MS = 10 * 60 * 1000

        for consumer in consumers:
            if (
                consumer["name"] != CONSUMER_NAME
                and consumer["idle"] > TEN_MIN_MS
                and consumer["pending"] == 0
            ):
                logger.info(f"🗑 Removing dead consumer {consumer['name']}")
                await redis_client.xgroup_delconsumer(
                    EVENT_STREAM_NAME,
                    CONSUMER_GROUP,
                    consumer["name"],
                )

    except Exception as e:
        logger.error(f"Cleanup error: {e}")


# ==========================================================
# WORKER LOOP (NOW MATCHES YOUR OTHER SERVICES)
# ==========================================================
async def worker_loop():
    last_cleanup = 0

    heartbeat_task = asyncio.create_task(send_heartbeat())

    logger.info("🔁 Startup recovery...")
    await recover_pending_messages()
    await cleanup_dead_consumers()

    try:
        while True:
            now = asyncio.get_running_loop().time()

            if now - last_cleanup > CLEANUP_INTERVAL:
                await cleanup_dead_consumers()
                last_cleanup = now

            entries = await event_stream.read_group(
                group_name=CONSUMER_GROUP,
                consumer_name=CONSUMER_NAME,
                count=BATCH_SIZE,
                block_ms=5000,
            )

            for msg_id, data in entries:
                try:
                    await process_message(msg_id, data)
                except Exception as e:
                    logger.error(f"❌ Error processing {msg_id}: {e}")

    except asyncio.CancelledError:
        logger.warning("🛑 Worker loop cancelled — shutting down")

    finally:
        heartbeat_task.cancel()

        await asyncio.gather(
            heartbeat_task,
            return_exceptions=True,
        )

        await redis_client.delete(HEARTBEAT_KEY)


# ==========================================================
# SIGNAL HANDLING
# ==========================================================
def setup_signal_handlers(loop, worker_task):
    async def shutdown():
        logger.info("🛑 Shutdown signal received")
        worker_task.cancel()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig,
            lambda: asyncio.create_task(shutdown()),
        )


# ==========================================================
# MAIN
# ==========================================================
async def main():
    await setup_consumer_group()

    logger.info("💨 Starting Sentiment Analysis Service...")
    logger.info(f"📦 Consuming from: {EVENT_STREAM_NAME}")
    logger.info(f"📤 Writing to: {SENTIMENT_STREAM_NAME}")
    logger.info(f"👥 Consumer Group: {CONSUMER_GROUP}")
    logger.info(f"👤 Consumer Name: {CONSUMER_NAME}")
    logger.info(f"🔑 Heartbeat Key: {HEARTBEAT_KEY}")

    worker_task = asyncio.create_task(worker_loop())

    loop = asyncio.get_running_loop()
    setup_signal_handlers(loop, worker_task)

    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    finally:
        logger.info("🧹 Shutting down...")

        if not worker_task.done():
            worker_task.cancel()

        await asyncio.gather(worker_task, return_exceptions=True)

        await redis_client.aclose()


if __name__ == "__main__":
    asyncio.run(main())