import asyncio
import json
import signal
import uuid
import redis.asyncio as redis
from app.utils.logger import setup_logging
from app.core.config import env_config
from app.services._03_event_identification import EventIdentifierService
from app.scripts.storage import RedisStreamStorage
from app.scripts.aws_bucket_access import AWSBucket

logger = setup_logging()

# ================= CONFIG =================
TICKER_STREAM_NAME = env_config.redis_ticker_stream
EVENT_STREAM_NAME = env_config.redis_event_stream

REMOVED_POSTS_COUNTER = "eventidentification:removed_posts_count"

CONSUMER_GROUP = "eventidentification_group"
CONSUMER_NAME = f"eventidentification_{uuid.uuid4().hex[:6]}"

HEARTBEAT_KEY = f"event_identification:heartbeat:{CONSUMER_NAME}"
HEARTBEAT_INTERVAL = 30
HEARTBEAT_TTL = HEARTBEAT_INTERVAL * 3

EVENT_LIST_REDIS_KEY = "event_service:event_list"

EVENT_LIST_LOCK_KEY = "event_service:event_list:lock"
EVENT_LIST_LOCK_TTL = 30

PERSIST_INTERVAL = 1800
TICKER_FLUSH_INTERVAL = 900

BATCH_SIZE = 10
RECOVER_BATCH_SIZE = 100
MIN_IDLE_MS = 5000
CLEANUP_INTERVAL = 300


# ================= INIT (Infrastructure Only) =================
bucket = AWSBucket()

redis_client = redis.Redis(
    host=env_config.redis_host,
    port=int(env_config.redis_port),
    password=env_config.redis_password,
    decode_responses=True,
)

ticker_stream = RedisStreamStorage(TICKER_STREAM_NAME, redis_client)
event_stream = RedisStreamStorage(EVENT_STREAM_NAME, redis_client)

all_tickers = set()


# ==========================================================
# 🔥 LOAD EVENT LIST
# ==========================================================
async def load_event_list():
    data = await redis_client.get(EVENT_LIST_REDIS_KEY)

    if data:
        logger.info("✅ Loaded event list from Redis")
        return json.loads(data)

    logger.info("⚡ No event list in Redis — loading from bucket")

    bucket_data = bucket.read_text(env_config.aws_bucket_events_key)
    await redis_client.set(EVENT_LIST_REDIS_KEY, bucket_data)

    return json.loads(bucket_data)


# ================= BACKGROUND PERSIST =================
async def persist_event_list_to_bucket():
    try:
        while True:
            await asyncio.sleep(PERSIST_INTERVAL)

            data = await redis_client.get(EVENT_LIST_REDIS_KEY)
            if data:
                bucket.write_text(data, env_config.aws_bucket_events_key)
                logger.info("💾 Synced event list Redis → Bucket")

    except asyncio.CancelledError:
        logger.warning("🛑 Persist task stopped")
        raise

# ================= PERIODIC TICKER FLUSH (🔥 NEW) =================
async def periodic_ticker_flush(event_service: EventIdentifierService):
    """
    Flush tickers to Redis every 15 minutes.
    This prevents constant writes under scale.
    """

    try:
        while True:
            await asyncio.sleep(TICKER_FLUSH_INTERVAL)

            await flush_tickers(event_service)

    except asyncio.CancelledError:
        logger.warning("🛑 Ticker flush task stopped")
        raise


# ================= ACTUAL FLUSH LOGIC =================
async def flush_tickers(event_service: EventIdentifierService):
    """
    Write tickers to Redis.
    Called every 15 minutes + on shutdown.
    """
    logger.info("🔥 Flush function entered")

    if not all_tickers:
        logger.info("🟡 Nothing to flush")
        return

    logger.info(f"🚀 Flushing {len(all_tickers)} tickers to Redis")

    for ticker in all_tickers:
        await redis_client.hset(
            "event_service:all_identified_tickers",
            ticker,
            "1",  # or store metadata if needed
        )

    logger.info("✅ Tick list flushed")
    all_tickers.clear()

# ================= GROUP SETUP =================
async def setup_consumer_group():
    try:
        await ticker_stream.create_consumer_group(
            CONSUMER_GROUP,
            start_id="0",
            mkstream=True,
        )
        logger.info(f"✅ Consumer group {CONSUMER_GROUP} ready")
    except Exception:
        logger.info("Group likely already exists")


async def finalize_message(msg_id: str):
    await ticker_stream.acknowledge(CONSUMER_GROUP, msg_id)
    await ticker_stream.delete(msg_id)


# ================= EVENT LIST UPDATE (LOCK PROTECTED) =================
async def update_event_list_in_redis(event_service: EventIdentifierService):
    logger.info(f"check event count here: {event_service.neweventcount}")
    if event_service.neweventcount <= 0:
        return

    lock = redis_client.lock(
        EVENT_LIST_LOCK_KEY,
        timeout=EVENT_LIST_LOCK_TTL,
        blocking_timeout=5,
    )
    async with lock:
        logger.info("🔒 Lock acquired — updating event list")

        latest = await redis_client.get(EVENT_LIST_REDIS_KEY)
        latest_events = json.loads(latest) if latest else {}

        # Merge safely
        merged = {**latest_events, **event_service.event_list}

        await redis_client.set(
            EVENT_LIST_REDIS_KEY,
            json.dumps(merged, indent=2),
        )

        event_service.neweventcount = 0

        logger.info("✅ Event list updated in Redis")
        logger.info("🔓 Released lock")


# ================= HELPERS =================
def decode_message(data: dict):
    raw = data.get("data")

    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON decode failed: {e}")
            return None

    return raw if isinstance(raw, dict) else data


def normalize_proposed_events(ticker_metadata: dict):
    for ticker, info in ticker_metadata.items():
        proposal = info.get("event_proposal")

        if proposal:
            proposed_event_name = proposal.get("proposed_event_name")
            if proposed_event_name:
                logger.info(
                    f"🔄 Converting proposal → event_type for {ticker}: {proposed_event_name}"
                )
                info["event_type"] = proposed_event_name


# ================= MESSAGE PROCESSING =================
async def process_message(
    msg_id: str,
    data: dict,
    event_service: EventIdentifierService,
):
    decoded = decode_message(data)
    if not decoded:
        await finalize_message(msg_id)
        return

    event_data = event_service.analyse_event(decoded)
    if not event_data:
        await finalize_message(msg_id)
        return

    # 🔥 Update event list only if new event detected
    await update_event_list_in_redis(event_service)

    post_id = event_data.get("id")
    ticker_metadata = event_data.get("ticker_metadata", {})

    normalize_proposed_events(ticker_metadata)

    ticker_metadata = {
        ticker: info
        for ticker, info in ticker_metadata.items()
        if info.get("event_type") is not None
    }

    if not ticker_metadata:
        await redis_client.incr(REMOVED_POSTS_COUNTER)
        await finalize_message(msg_id)
        return

    event_data["ticker_metadata"] = ticker_metadata
    all_tickers.update(ticker_metadata.keys())
    
    logger.info(f"📊 Tracked tickers: {all_tickers}")

    try:
        await event_stream.save(event_data)
    except asyncio.CancelledError:
        raise

    await finalize_message(msg_id)

    logger.info(f"✅ Processed Post {post_id}")


# ================= RECOVERY =================
async def recover_pending_messages(event_service: EventIdentifierService):
    claimed = await ticker_stream.claim_pending(
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
            await process_message(msg_id, data, event_service)
        except Exception as e:
            logger.error(f"❌ Recovery failed {msg_id}: {e}")


# ================= CLEANUP =================
async def cleanup_dead_consumers():
    try:
        consumers = await redis_client.xinfo_consumers(
            TICKER_STREAM_NAME,
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
                    TICKER_STREAM_NAME,
                    CONSUMER_GROUP,
                    consumer["name"],
                )

    except Exception as e:
        logger.error(f"Cleanup error: {e}")


# ================= HEARTBEAT =================
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
        logger.error("🛑 Heartbeat stopped")
        raise


# ================= WORKER LOOP =================
async def worker_loop(event_service: EventIdentifierService):
    last_cleanup = 0

    heartbeat_task = asyncio.create_task(send_heartbeat())
    persist_task = asyncio.create_task(persist_event_list_to_bucket())
    ticker_flush_task = asyncio.create_task(
        periodic_ticker_flush(event_service)
    )


    logger.info("🔁 Startup recovery...")
    await recover_pending_messages(event_service)
    await cleanup_dead_consumers()

    try:
        while True:
            now = asyncio.get_running_loop().time()

            if now - last_cleanup > CLEANUP_INTERVAL:
                await cleanup_dead_consumers()
                last_cleanup = now

            entries = await ticker_stream.read_group(
                group_name=CONSUMER_GROUP,
                consumer_name=CONSUMER_NAME,
                count=BATCH_SIZE,
                block_ms=5000,
            )

            for msg_id, data in entries:
                try:
                    await process_message(msg_id, data, event_service)
                except Exception as e:
                    logger.error(f"❌ Error processing {msg_id}: {e}")

    except asyncio.CancelledError:
        logger.warning("🛑 Worker loop cancelled — shutting down cleanly")
        raise

    finally:
        await flush_tickers(event_service)
        heartbeat_task.cancel()
        persist_task.cancel()
        ticker_flush_task.cancel()

        await asyncio.gather(
            heartbeat_task,
            persist_task,
            ticker_flush_task,
            return_exceptions=True,
        )


# ================= SHUTDOWN =================
def setup_signal_handlers(loop, worker_task):
    async def shutdown():
        logger.info("🛑 Shutdown signal received")
        worker_task.cancel()
        await redis_client.delete(HEARTBEAT_KEY)

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig,
            lambda: asyncio.create_task(shutdown()),
        )


# ================= MAIN =================
async def main():
    await setup_consumer_group()

    events_types = await load_event_list()

    # ✅ Dependency created here
    event_service = EventIdentifierService(event_list=events_types)

    logger.info("💨 Starting Event Identification Service...")
    logger.info(f"📦 Consuming from: {TICKER_STREAM_NAME}")
    logger.info(f"📤 Writing to: {EVENT_STREAM_NAME}")
    logger.info(f"👥 Consumer Group: {CONSUMER_GROUP}")
    logger.info(f"👤 Consumer Name: {CONSUMER_NAME}")
    logger.info(f"🔑 Heartbeat Key: {HEARTBEAT_KEY}")

    worker_task = asyncio.create_task(worker_loop(event_service))

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