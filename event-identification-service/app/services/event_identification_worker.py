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
from datetime import datetime
from zoneinfo import ZoneInfo

logger = setup_logging()

# ==========================================================
# CONFIG
# ==========================================================
TICKER_STREAM_NAME = env_config.redis_ticker_stream
EVENT_STREAM_NAME = env_config.redis_event_stream

REMOVED_POSTS_COUNTER = "eventidentification:removed_posts_count"
DUP_POSTS_COUNTER = "eventidentification:duplicate_posts_count"

CONSUMER_GROUP = "eventidentification_group"
CONSUMER_NAME = f"eventidentification_{uuid.uuid4().hex[:6]}"

HEARTBEAT_KEY = f"eventidentification:heartbeat:{CONSUMER_NAME}"
HEARTBEAT_INTERVAL = 30
HEARTBEAT_TTL = HEARTBEAT_INTERVAL * 3

EVENT_LIST_REDIS_KEY = "eventidentification:event_list"

EVENT_LIST_LOCK_KEY = "eventidentification:event_list:lock"
EVENT_LIST_LOCK_TTL = 30

PERSIST_INTERVAL = 1800
TICKER_FLUSH_INTERVAL = 900
TICKER_KEY = "eventidentification:ticker"

BATCH_SIZE = 3
RECOVER_BATCH_SIZE = 10
MIN_IDLE_MS = 30000
CLEANUP_INTERVAL = 300

POST_TIMESTAMP = "post_timestamps"

# ==========================================================
# RATE LIMITING
# ==========================================================
LLM_CONCURRENCY = 3
_llm_semaphore = asyncio.Semaphore(LLM_CONCURRENCY)

_last_event_list_update = 0.0
EVENT_LIST_DEBOUNCE = 60.0

# ==========================================================
# INIT
# ==========================================================
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
# LOAD EVENT LIST
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


# ==========================================================
# BACKGROUND PERSIST
# ==========================================================
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


# ==========================================================
# PERIODIC TICKER FLUSH (15 MINUTES)
# ==========================================================
async def periodic_ticker_flush(event_service: EventIdentifierService):
    try:
        while True:
            await asyncio.sleep(TICKER_FLUSH_INTERVAL)
            await flush_tickers(event_service)
    except asyncio.CancelledError:
        logger.warning("🛑 Ticker flush task stopped")
        raise


async def flush_tickers(event_service: EventIdentifierService):
    logger.info("🔥 Flush function entered")

    if not all_tickers:
        logger.info("🟡 Nothing to flush")
        return

    logger.info(f"🚀 Flushing {len(all_tickers)} tickers to Redis")

    SEVEN_DAYS = 60 * 60 * 24 * 7

    pipe = redis_client.pipeline()
    for ticker in all_tickers:
        pipe.set(
            f"{TICKER_KEY}:{ticker}",
            datetime.now(ZoneInfo("Asia/Singapore")).isoformat(),
            ex=SEVEN_DAYS,
        )
    await pipe.execute()

    logger.info("✅ Tickers flushed")
    all_tickers.clear()


# ==========================================================
# CONSUMER GROUP
# ==========================================================
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


# ==========================================================
# EVENT LIST UPDATE (LOCK PROTECTED + DEBOUNCED)
# ==========================================================
async def update_event_list_in_redis(event_service: EventIdentifierService):
    global _last_event_list_update

    if event_service.neweventcount <= 0:
        return

    now = asyncio.get_event_loop().time()
    if now - _last_event_list_update < EVENT_LIST_DEBOUNCE:
        return

    _last_event_list_update = now

    lock = redis_client.lock(
        EVENT_LIST_LOCK_KEY,
        timeout=EVENT_LIST_LOCK_TTL,
        blocking_timeout=5,
    )

    async with lock:
        logger.info("🔒 Lock acquired — updating event list")

        latest = await redis_client.get(EVENT_LIST_REDIS_KEY)
        latest_events = json.loads(latest) if latest else {}

        merged = {**latest_events, **event_service.event_list}

        await redis_client.set(
            EVENT_LIST_REDIS_KEY,
            json.dumps(merged, indent=2),
        )

        event_service.neweventcount = 0

        logger.info("✅ Event list updated in Redis")
        logger.info("🔓 Released lock")


# ==========================================================
# HELPERS
# ==========================================================
def decode_message(data: dict):
    raw = data.get("data")

    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON decode failed: {e}")
            return None

    return raw if isinstance(raw, dict) else data


# check if scraped news has already been processed before 
async def is_duplicate(post_id: str) -> bool:
    dedup_key = f"event_dedup:{post_id}"
    return await redis_client.exists(dedup_key)

# ==========================================================
# MESSAGE PROCESSING
# ==========================================================
async def process_message(
    msg_id: str,
    data: dict,
    event_service: EventIdentifierService,
):
    decoded = decode_message(data)
    if not decoded:
        await redis_client.incr(REMOVED_POSTS_COUNTER)
        await finalize_message(msg_id)
        return

    sg_now = datetime.now(ZoneInfo("Asia/Singapore")).isoformat()
    post_id = decoded.get("id", "").strip('"')

    if await is_duplicate(post_id):
        logger.info(f"⚠️ Duplicate post {post_id} — skipping")
        await redis_client.incr(DUP_POSTS_COUNTER)
        await finalize_message(msg_id)
        return

    await redis_client.hset(
        f"{POST_TIMESTAMP}:{post_id}",
        "event_timestamp_start",
        sg_now,
    )
    print(f"⏱️ Post {post_id}: Timestamped at event Stage (Start) → {sg_now}")

    async with _llm_semaphore:
        event_data = await event_service.analyse_event(decoded)

    if not event_data:
        await redis_client.incr(REMOVED_POSTS_COUNTER)
        await finalize_message(msg_id)
        return

    await update_event_list_in_redis(event_service)

    post_id = event_data.get("id", "").strip('"')
    ticker_metadata = event_data.get("ticker_metadata", {})

    # ✅ proposal conversion is now done inside the service
    # worker just filters on event_type directly
    ticker_metadata = {
        ticker: info
        for ticker, info in ticker_metadata.items()
        if info.get("event_type") is not None
    }

    if not ticker_metadata:
        logger.info(f"🗑 Removing post {post_id} as there is no event identified.")
        await redis_client.incr(REMOVED_POSTS_COUNTER)
        await finalize_message(msg_id)
        return

    event_data["ticker_metadata"] = ticker_metadata
    metadata = event_data.get("metadata", {})
    ticker_check = metadata.get("ticker")
    if not ticker_check:
        all_tickers.update(ticker_metadata.keys())

    logger.info(f"📊 Tracked tickers: {all_tickers}")

    try:
        await event_stream.save(event_data)
    except asyncio.CancelledError:
        raise

    sg_now = datetime.now(ZoneInfo("Asia/Singapore")).isoformat()
    await redis_client.hset(
        f"{POST_TIMESTAMP}:{post_id}",
        "event_timestamp",
        sg_now,
    )
    print(f"⏱️ Post {post_id}: Timestamped at event Stage → {sg_now}")

    await ticker_stream.acknowledge(CONSUMER_GROUP, msg_id)
    logger.info(f"✅ Processed Post {post_id}")


# ==========================================================
# RECOVERY
# ==========================================================
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

    tasks = [
        process_message(msg_id, data, event_service)
        for msg_id, data in claimed
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"❌ Recovery failed for message {i}: {result}")


# ==========================================================
# CLEANUP
# ==========================================================
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
        logger.error("🛑 Heartbeat stopped")
        raise


# ==========================================================
# WORKER LOOP
# ==========================================================
async def worker_loop(event_service: EventIdentifierService):
    last_cleanup = 0

    heartbeat_task = asyncio.create_task(send_heartbeat())
    persist_task = asyncio.create_task(persist_event_list_to_bucket())
    ticker_flush_task = asyncio.create_task(periodic_ticker_flush(event_service))

    # non-blocking — new messages consumed immediately
    asyncio.create_task(recover_pending_messages(event_service))
    asyncio.create_task(cleanup_dead_consumers())

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
                block_ms=1000,
            )

            if entries:
                tasks = [
                    process_message(msg_id, data, event_service)
                    for msg_id, data in entries
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        logger.error(f"❌ Error processing message {i}: {result}")

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


# ==========================================================
# SHUTDOWN
# ==========================================================
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


# ==========================================================
# MAIN
# ==========================================================
async def main():
    await setup_consumer_group()

    events_types = await load_event_list()
    event_service = EventIdentifierService(event_list=events_types)

    logger.info("💨 Starting Event Identification Service...")
    logger.info(f"📦 Consuming from: {TICKER_STREAM_NAME}")
    logger.info(f"📤 Writing to: {EVENT_STREAM_NAME}")
    logger.info(f"👥 Consumer Group: {CONSUMER_GROUP}")
    logger.info(f"👤 Consumer Name: {CONSUMER_NAME}")
    logger.info(f"🔑 Heartbeat Key: {HEARTBEAT_KEY}")
    logger.info(f"⚡ LLM concurrency: {LLM_CONCURRENCY} (semaphore, no sleep)")

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