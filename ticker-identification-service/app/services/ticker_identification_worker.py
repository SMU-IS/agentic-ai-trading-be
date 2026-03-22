import asyncio
import json
import signal
import uuid
import redis.asyncio as redis
from app.utils.logger import setup_logging
from app.core.config import env_config
from app.services._02_ticker_identification import TickerIdentificationService
from app.scripts.storage import RedisStreamStorage
from app.scripts.aws_bucket_access import AWSBucket
from datetime import datetime
from zoneinfo import ZoneInfo

logger = setup_logging()


# ==========================================================
# CONFIG
# ==========================================================
TICKER_STREAM_NAME = env_config.redis_ticker_stream
PREPROC_STREAM_NAME = env_config.redis_preproc_stream

REMOVED_POSTS_COUNTER = "tickeridentification:removed_posts_count"
DUP_POSTS_COUNTER = "tickeridentification:duplicate_posts_count"


CONSUMER_GROUP = "tickeridentification_group"
CONSUMER_NAME = f"tickeridentification_{uuid.uuid4().hex[:6]}"

HEARTBEAT_KEY = f"tickeridentification:heartbeat:{CONSUMER_NAME}"
HEARTBEAT_INTERVAL = 30
HEARTBEAT_TTL = HEARTBEAT_INTERVAL * 3

CLEANED_REDIS_KEY = "tickeridentification:cleaned_tickers"
ALIAS_REDIS_KEY = "tickeridentification:alias_mapping"

PERSIST_INTERVAL = 1800
TICKER_FLUSH_INTERVAL = 900

BATCH_SIZE = 50
RECOVER_BATCH_SIZE = 100
MIN_IDLE_MS = 5000
CLEANUP_INTERVAL = 300

TICKER_LIST_LOCK_KEY = "ticker_static_state_write_lock"
TICKER_LIST_LOCK_TTL = 30

POST_TIMESTAMP = "post_timestamps"

# ==========================================================
# RATE LIMITING
# ==========================================================
LLM_CONCURRENCY = 3
_llm_semaphore = asyncio.Semaphore(LLM_CONCURRENCY)

_last_persist_time = 0.0
PERSIST_DEBOUNCE = 60.0

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

preproc_stream = RedisStreamStorage(PREPROC_STREAM_NAME, redis_client)
ticker_stream = RedisStreamStorage(TICKER_STREAM_NAME, redis_client)


# ==========================================================
# LOAD STATIC STATE (Redis → S3 Fallback)
# ==========================================================
async def load_static_state(redis_key: str, bucket_key: str):
    data = await redis_client.get(redis_key)

    if data:
        logger.info(f"✅ Loaded {redis_key} from Redis")
        return json.loads(data)

    logger.info(f"⚡ Redis empty — loading {redis_key} from bucket")

    raw = bucket.read_text(bucket_key)

    await redis_client.set(redis_key, raw)

    return json.loads(raw)


async def init_ticker_service():
    cleaned_tickers = await load_static_state(
        CLEANED_REDIS_KEY,
        env_config.aws_bucket_cleaned_key,
    )

    alias_to_canonical = await load_static_state(
        ALIAS_REDIS_KEY,
        env_config.aws_bucket_alias_key,
    )

    return TickerIdentificationService(
        cleaned_tickers=cleaned_tickers,
        alias_to_canonical=alias_to_canonical,
    )


# ==========================================================
# CONSUMER GROUP
# ==========================================================
async def setup_consumer_group():
    try:
        await preproc_stream.create_consumer_group(
            CONSUMER_GROUP,
            start_id="0",
            mkstream=True,
        )
        logger.info(f"✅ Consumer group {CONSUMER_GROUP} ready")
    except Exception:
        logger.info("Group likely already exists")


async def finalize_message(msg_id: str):
    await preproc_stream.acknowledge(CONSUMER_GROUP, msg_id)
    await preproc_stream.delete(msg_id)


# ==========================================================
# PERIODIC TICKER FLUSH (15 MINUTES)
# ==========================================================
async def flush_tickers_periodically(ticker_service: TickerIdentificationService):
    try:
        while True:
            await asyncio.sleep(TICKER_FLUSH_INTERVAL)
            await flush_tickers(ticker_service)

    except asyncio.CancelledError:
        logger.warning("🛑 Ticker flush task stopped")
        raise


async def flush_tickers(ticker_service: TickerIdentificationService):
    tickers = await load_all_tickers_from_event_service()
    if not tickers:
        logger.info("🟡 No tickers found in event service")
        return

    logger.info(f"🚀 Enriching {len(tickers)} tickers")

    aliases = ticker_service.get_aliases(list(tickers))

    pipe = redis_client.pipeline()

    for ticker, data in aliases.items():
        pipe.hset(
            "all_identified_tickers",
            ticker,
            json.dumps(data),
        )

    await pipe.execute()

    logger.info("✅ Tickers flushed")


# ==========================================================
# DISTRIBUTED LOCK FOR STATIC STATE WRITES
# ==========================================================
async def persist_if_changed(ticker_service: TickerIdentificationService):
    global _last_persist_time

    if (
        ticker_service.new_alias_count <= 0
        and ticker_service.new_type_count <= 0
    ):
        return

    now = asyncio.get_event_loop().time()
    if now - _last_persist_time < PERSIST_DEBOUNCE:
        return

    _last_persist_time = now

    lock = redis_client.lock(
        TICKER_LIST_LOCK_KEY,
        timeout=TICKER_LIST_LOCK_TTL,
        blocking_timeout=5,
    )

    async with lock:
        logger.info("🔒 Lock acquired — updating alias mapping / cleaned tickers")

        if ticker_service.new_alias_count > 0:
            logger.info(f"{ticker_service.new_alias_count} new aliases added")

            alias_json = json.dumps(
                ticker_service.alias_to_canonical,
                indent=2,
            )

            await redis_client.set(ALIAS_REDIS_KEY, alias_json)
            ticker_service.new_alias_count = 0
            logger.info("✅ Alias mapping updated")

        if ticker_service.cleaned_tickers and ticker_service.new_type_count > 0:
            logger.info(f"{ticker_service.new_type_count} new ticker types added")

            cleaned_json = json.dumps(
                ticker_service.cleaned_tickers,
                indent=2,
            )

            await redis_client.set(CLEANED_REDIS_KEY, cleaned_json)
            ticker_service.new_type_count = 0
            logger.info("✅ Cleaned ticker list updated")

        logger.info("🔓 Released lock")


# ==========================================================
# BACKGROUND SAFETY PERSIST
# ==========================================================
async def persist_static_state():
    try:
        while True:
            await asyncio.sleep(PERSIST_INTERVAL)

            for key, bucket_key in [
                (CLEANED_REDIS_KEY, env_config.aws_bucket_cleaned_key),
                (ALIAS_REDIS_KEY, env_config.aws_bucket_alias_key),
            ]:
                data = await redis_client.get(key)
                if data:
                    bucket.write_text(data, bucket_key)

            logger.info("💾 Synced alias mapping and cleaned tickers Redis → Bucket")

    except asyncio.CancelledError:
        logger.warning("🛑 Persist task stopped")
        raise


# ==========================================================
# SYNC WITH EVENT IDENTIFIER
# ==========================================================
async def load_all_tickers_from_event_service():
    tickers = await redis_client.hkeys(
        "eventidentification:all_identified_tickers"
    )

    logger.info(f"📥 Loaded {len(tickers)} tickers from event service")

    return set(tickers)


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

# check if scraped news has already been processed before 
async def is_duplicate(post_id: str) -> bool:
    dedup_key = f"ticker_dedup:{post_id}"
    return await redis_client.exists(dedup_key)

# ==========================================================
# MESSAGE PROCESSING
# ==========================================================
def decode_message(data: dict):
    raw = data.get("data")

    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    return raw if isinstance(raw, dict) else data


async def process_message(msg_id: str, data: dict, ticker_service: TickerIdentificationService):
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
        "ticker_timestamp_start",
        sg_now,
    )
    print(f"⏱️ Post {post_id}: Timestamped at ticker Stage (Start) → {sg_now}")

    async with _llm_semaphore:
        tickers_post = await ticker_service.process_post(decoded)

    if not tickers_post:
        await redis_client.incr(REMOVED_POSTS_COUNTER)
        await finalize_message(msg_id)
        return

    ticker_metadata = tickers_post.get("ticker_metadata", {})
    post_id = tickers_post.get("id", "").strip('"')

    if not ticker_metadata:
        logger.info(f"🗑 Removing post {post_id} as there is no ticker identified.")
        await redis_client.incr(REMOVED_POSTS_COUNTER)
        await finalize_message(msg_id)
        return

    try:
        await ticker_stream.save(tickers_post)
    except asyncio.CancelledError:
        raise

    sg_now = datetime.now(ZoneInfo("Asia/Singapore")).isoformat()
    await redis_client.hset(
        f"{POST_TIMESTAMP}:{post_id}",
        "ticker_timestamp",
        sg_now,
    )
    print(f"⏱️ Post {post_id}: Timestamped at ticker Stage → {sg_now}")

    await preproc_stream.acknowledge(CONSUMER_GROUP, msg_id)
    logger.info(f"✅ Processed Post {post_id}")

    await persist_if_changed(ticker_service)


# ==========================================================
# RECOVERY
# ==========================================================
async def recover_pending_messages(ticker_service):
    claimed = await preproc_stream.claim_pending(
        group_name=CONSUMER_GROUP,
        consumer_name=CONSUMER_NAME,
        min_idle_time_ms=MIN_IDLE_MS,
        count=RECOVER_BATCH_SIZE,
    )

    if not claimed:
        return

    logger.info(f"⚡ Recovered {len(claimed)} messages")

    tasks = [
        process_message(msg_id, data, ticker_service)
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
            PREPROC_STREAM_NAME,
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
                    PREPROC_STREAM_NAME,
                    CONSUMER_GROUP,
                    consumer["name"],
                )

    except Exception as e:
        logger.error(f"Cleanup error: {e}")


# ==========================================================
# WORKER LOOP
# ==========================================================
async def worker_loop(ticker_service):
    last_cleanup = 0

    heartbeat_task = asyncio.create_task(send_heartbeat())
    persist_task = asyncio.create_task(persist_static_state())
    ticker_flush_task = asyncio.create_task(
        flush_tickers_periodically(ticker_service)
    )

    # non-blocking — new messages consumed immediately
    asyncio.create_task(recover_pending_messages(ticker_service))
    asyncio.create_task(cleanup_dead_consumers())

    try:
        while True:
            now = asyncio.get_running_loop().time()

            if now - last_cleanup > CLEANUP_INTERVAL:
                await cleanup_dead_consumers()
                last_cleanup = now

            entries = await preproc_stream.read_group(
                group_name=CONSUMER_GROUP,
                consumer_name=CONSUMER_NAME,
                count=BATCH_SIZE,
                block_ms=5000,
            )

            if entries:
                tasks = [
                    process_message(msg_id, data, ticker_service)
                    for msg_id, data in entries
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        logger.error(f"❌ Error processing message {i}: {result}")

    except asyncio.CancelledError:
        logger.error("🛑 Worker loop cancelled — shutting down cleanly")
        raise

    finally:
        await flush_tickers(ticker_service)
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

    ticker_service = await init_ticker_service()

    logger.info("💨 Starting Ticker Identification Service...")
    logger.info(f"📦 Consuming from: {PREPROC_STREAM_NAME}")
    logger.info(f"📤 Writing to: {TICKER_STREAM_NAME}")
    logger.info(f"👥 Consumer Group: {CONSUMER_GROUP}")
    logger.info(f"👤 Consumer Name: {CONSUMER_NAME}")
    logger.info(f"🔑 Heartbeat Key: {HEARTBEAT_KEY}")
    logger.info(f"⚡ LLM concurrency: {LLM_CONCURRENCY} (semaphore, no sleep)")

    worker_task = asyncio.create_task(worker_loop(ticker_service))

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