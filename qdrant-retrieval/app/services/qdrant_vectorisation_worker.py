import asyncio
import json
import signal
import uuid

import redis.asyncio as redis
from app.utils.logger import setup_logging
from app.core.config import env_config
from app.scripts.storage import RedisStreamStorage
from app.schemas.raw_news_payload import RedditSourcePayload
from app.services.vectorisation import VectorisationService

logger = setup_logging()

# ================= CONFIG =================
SENTIMENT_STREAM_NAME = env_config.redis_sentiment_stream
AGGREGATOR_STREAM_NAME = env_config.redis_aggregator_stream


CONSUMER_GROUP = "vectorisation_group"
CONSUMER_NAME = f"vectorisation_{uuid.uuid4().hex[:6]}"

HEARTBEAT_KEY = f"vectorisation:heartbeat:{CONSUMER_NAME}"
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

sentiment_stream = RedisStreamStorage(SENTIMENT_STREAM_NAME, redis_client)
aggregator_stream = RedisStreamStorage(AGGREGATOR_STREAM_NAME, redis_client)

vector_service = VectorisationService()


# ==========================================================
# GROUP SETUP
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


# ==========================================================
# FINALISE MESSAGE - ACK AND DELETE
# ==========================================================

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
# VECTORISATION
# ==========================================================
async def vectorise(payload: RedditSourcePayload):
    try:
        await vector_service.ensure_indexes()
        return await vector_service.get_sanitised_news_payload(payload)

    except Exception as e:
        logger.error(f"❌ Failed to vectorise post: {e}")
        return None


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

    for msg_id, data in claimed:
        try:
            decoded = decode_message(data)
            if not decoded:
                await finalize_message(msg_id)
                continue
            
            payload_dict = {"id": msg_id, "fields": decoded}
            payload = RedditSourcePayload.model_validate(payload_dict)
            post_id = decoded.get("id")

            result = await vectorise(payload)

            if not result:
                await finalize_message(msg_id)
                continue
                
            try:
                await aggregator_stream.save(decoded)
            except asyncio.CancelledError:
                raise

            # ✅ ACK after success
            await finalize_message(msg_id)

            logger.info(f"✅ Vectorised (recovered) Post {post_id}")

        except Exception as e:
            logger.error(f"❌ Recovery failed {msg_id}: {e}")


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

    logger.info("🔁 Startup recovery...")
    await recover_pending_messages()
    await cleanup_dead_consumers()

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
                block_ms=5000,
            )
            for msg_id, data in entries:
                try:
                    decoded = decode_message(data)
                    if not decoded:
                        await finalize_message(msg_id)
                        continue

                    payload_dict = {"id": msg_id, "fields": decoded}
                    payload = RedditSourcePayload.model_validate(payload_dict)
                    post_id = decoded.get("id")

                    result = await vectorise(payload)
                    if not result:
                        await finalize_message(msg_id)
                        continue
                    
                    try:
                        await aggregator_stream.save(decoded)
                    except asyncio.CancelledError:
                        raise

                    await finalize_message(msg_id)

                    logger.info(f"✅ Vectorised Post {post_id}")

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

        await redis_client.aclose()


if __name__ == "__main__":
    asyncio.run(main())