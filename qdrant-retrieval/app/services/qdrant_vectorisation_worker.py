import asyncio
import json
import signal
import uuid

import redis.asyncio as redis
from app.utils.logger import setup_logging
from app.core.config import env_config
from app.scripts.storage import RedisStreamStorage
from app.schemas.raw_news_payload import SourcePayload
from app.services.vectorisation import VectorisationService
# from app.scripts.postgres import save_post, mark_vectorised, close_pool, init_db
from datetime import datetime
from zoneinfo import ZoneInfo

logger = setup_logging()

# ==========================================================
# CONFIG
# ==========================================================
SENTIMENT_STREAM_NAME = env_config.redis_sentiment_stream
AGGREGATOR_STREAM_NAME = env_config.redis_aggregator_stream

CONSUMER_GROUP = "vectorisation_group"
CONSUMER_NAME = f"vectorisation_{uuid.uuid4().hex[:6]}"

HEARTBEAT_KEY = f"vectorisation:heartbeat:{CONSUMER_NAME}"
HEARTBEAT_INTERVAL = 30
HEARTBEAT_TTL = HEARTBEAT_INTERVAL * 3

BATCH_SIZE = 10
RECOVER_BATCH_SIZE = 10
MIN_IDLE_MS = 30000
CLEANUP_INTERVAL = 300

PROCESSED_POSTS_COUNTER = "vectorisation:processed_posts_count"
REMOVED_POSTS_COUNTER = "vectorisation:removed_posts_count"
DUP_POSTS_COUNTER = "vectorisation:duplicate_posts_count"

POST_TIMESTAMP = "post_timestamps"

# ==========================================================
# RETRY CONFIG
# ==========================================================
VECTORISE_MAX_RETRIES = 3
VECTORISE_RETRY_DELAY = 2.0


# ==========================================================
# INIT
# ==========================================================
redis_client = redis.Redis(
    host=env_config.redis_host,
    port=int(env_config.redis_port),
    password=env_config.redis_password,
    decode_responses=True,
)

sentiment_stream = RedisStreamStorage(SENTIMENT_STREAM_NAME, redis_client)
aggregator_stream = RedisStreamStorage(AGGREGATOR_STREAM_NAME, redis_client)

vector_service = VectorisationService()


# ==========================================================
# CONSUMER GROUP
# ==========================================================
async def setup_consumer_group():
    try:
        await sentiment_stream.create_consumer_group(
            CONSUMER_GROUP,
            start_id="0",
            mkstream=True,
        )
        logger.info(f"✅ Consumer group {CONSUMER_GROUP} ready")
    except Exception:
        logger.warning("Group likely already exists")


async def finalize_message(msg_id: str):
    await sentiment_stream.acknowledge(CONSUMER_GROUP, msg_id)
    await sentiment_stream.delete(msg_id)


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
# VECTORISE (with retries)
# ==========================================================
async def vectorise(payload: SourcePayload):
    for attempt in range(1, VECTORISE_MAX_RETRIES + 1):
        try:
            return await vector_service.get_sanitised_news_payload(payload)
        except Exception as e:
            logger.warning(f"[Vectorise] Attempt {attempt}/{VECTORISE_MAX_RETRIES} failed: {e}")
            if attempt < VECTORISE_MAX_RETRIES:
                await asyncio.sleep(VECTORISE_RETRY_DELAY * attempt)
            else:
                logger.error(f"[Vectorise] All {VECTORISE_MAX_RETRIES} attempts failed — dropping post")
                return None


# check if scraped news has already been processed before 
async def is_duplicate(post_id: str) -> bool:
    dedup_key = f"qdrant_dedup:{post_id}"
    return await redis_client.exists(dedup_key)

# ==========================================================
# MESSAGE PROCESSING
# ==========================================================
async def process_message(msg_id: str, data: dict):
    decoded = decode_message(data)
    if not decoded:
        await redis_client.incr(REMOVED_POSTS_COUNTER)
        await finalize_message(msg_id)
        return

    post_id = decoded.get("id", "").strip('"')

    if await is_duplicate(post_id):
        logger.info(f"⚠️ Duplicate post {post_id} — skipping")
        await redis_client.incr(DUP_POSTS_COUNTER)
        await finalize_message(msg_id)
        return

    payload_dict = {"id": msg_id, "fields": decoded}
    try:
        payload = SourcePayload.model_validate(payload_dict)
    except Exception as e:
        logger.error(f"❌ Failed to validate payload for {post_id}: {e}")
        await redis_client.incr(REMOVED_POSTS_COUNTER)
        await finalize_message(msg_id)
        return
    
    await redis_client.hset(
        f"{POST_TIMESTAMP}:{post_id}",
        "qdrant_timestamp_start",
        datetime.now(ZoneInfo("Asia/Singapore")).isoformat(),
    )

    # 1. save to postgres before vectorising — always recorded regardless of outcome
    # try:
    #     await save_post(decoded, vectorised=False)
    # except Exception as e:
    #     logger.error(f"❌ Postgres save failed for {post_id}: {e}")
        # non-fatal — continue to vectorise even if postgres fails

    # 2. vectorise
    result = await vectorise(payload)
    if not result:
        await redis_client.incr(REMOVED_POSTS_COUNTER)
        await finalize_message(msg_id)
        return

    # 3. mark as vectorised in postgres
    # try:
    #     await mark_vectorised(post_id)
    # except Exception as e:
    #     logger.error(f"❌ Postgres update failed for {post_id}: {e}")
        # non-fatal — qdrant write succeeded, don't drop the post

    # 4. save to aggregator stream and finalize
    try:
        await aggregator_stream.save(decoded)

        sg_now = datetime.now(ZoneInfo("Asia/Singapore")).isoformat()
        await redis_client.hset(
            f"{POST_TIMESTAMP}:{post_id}",
            "qdrant_timestamp",
            sg_now,
        )
        logger.info(f"⏱️ Post {post_id}: Timestamped at qdrant Stage → {sg_now}")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"❌ Post-vectorisation step failed for {post_id}: {e}")

    await finalize_message(msg_id)
    await redis_client.incr(PROCESSED_POSTS_COUNTER)
    logger.info(f"✅ Vectorised Post {post_id}")


# ==========================================================
# RECOVERY
# ==========================================================
async def recover_pending_messages():
    claimed = await sentiment_stream.claim_pending(
        group_name=CONSUMER_GROUP,
        consumer_name=CONSUMER_NAME,
        min_idle_time_ms=MIN_IDLE_MS,
        count=RECOVER_BATCH_SIZE,
    )

    if not claimed:
        return

    logger.info(f"⚡ Recovered {len(claimed)} messages")

    tasks = [
        process_message(msg_id, data)
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
            SENTIMENT_STREAM_NAME,
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
                    SENTIMENT_STREAM_NAME,
                    CONSUMER_GROUP,
                    consumer["name"],
                )

    except Exception as e:
        logger.error(f"Cleanup error: {e}")


# ==========================================================
# WORKER LOOP
# ==========================================================
async def worker_loop():
    last_cleanup = 0

    heartbeat_task = asyncio.create_task(send_heartbeat())

    # non-blocking — new messages consumed immediately
    asyncio.create_task(recover_pending_messages())
    asyncio.create_task(cleanup_dead_consumers())

    try:
        while True:
            now = asyncio.get_running_loop().time()

            if now - last_cleanup > CLEANUP_INTERVAL:
                await cleanup_dead_consumers()
                last_cleanup = now

            entries = await sentiment_stream.read_group(
                group_name=CONSUMER_GROUP,
                consumer_name=CONSUMER_NAME,
                count=BATCH_SIZE,
                block_ms=1000,
            )

            if entries:
                tasks = [
                    process_message(msg_id, data)
                    for msg_id, data in entries
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        logger.error(f"❌ Error processing message {i}: {result}")

    except asyncio.CancelledError:
        logger.warning("🛑 Worker loop cancelled — shutting down")
        raise

    finally:
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)
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

    # ✅ init postgres table (idempotent — safe to run every startup)
    # await init_db()

    # ✅ ensure qdrant indexes once at startup
    await vector_service.ensure_indexes()
    logger.info("✅ Qdrant indexes ready")

    logger.info("💨 Starting Vectorisation Service...")
    logger.info(f"📦 Consuming from: {SENTIMENT_STREAM_NAME}")
    logger.info(f"📤 Writing to Qdrant and {AGGREGATOR_STREAM_NAME}")
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
        # await close_pool()       # ← close postgres pool
        await redis_client.aclose()


if __name__ == "__main__":
    asyncio.run(main())