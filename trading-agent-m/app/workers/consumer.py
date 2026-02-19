import asyncio
import json
import logging

import redis.asyncio as redis  # type: ignore
from app.core.config import env_config
from app.services.trading_workflow import TradingWorkflow
from langchain_perplexity import ChatPerplexity


logger = logging.getLogger("TradingWorker")


async def start_consumer():
    """
    The dedicated background worker.
    It owns its own resources (Redis connection, Agent instance).
    """

    logger.info(f"👷 Starting Worker: {env_config.redis_worker_name}")

    redis_client = redis.from_url(env_config.redis_url, decode_responses=True)

    llm = ChatPerplexity(
        pplx_api_key=env_config.perplexity_api_key,  # PPLX_API_KEY env var [web:11]
        model=env_config.perplexity_model,  # Search-enabled model for trading/news [web:19][web:21]
        temperature=env_config.perplexity_temperature or 0.2,
    )

    # Initialise the trading workflow agent
    agent = TradingWorkflow(llm_client=llm)

    # 2. Ensure Group Exists
    try:
        await redis_client.xgroup_create(
            env_config.redis_stream_key, env_config.redis_group_name, mkstream=True
        )
    except redis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            logger.error(f"Group Creation Error: {e}")

    # 3. The Infinite Loop
    try:
        while True:
            # logger.info("📖 Reading messages from Redis Stream")
            try:
                streams = await redis_client.xreadgroup(
                    env_config.redis_group_name,
                    env_config.redis_worker_name,
                    {env_config.redis_stream_key: ">"},
                    count=1,
                    block=5000,
                )

                if not streams:
                    await asyncio.sleep(0.1)
                    continue

                for _, messages in streams:
                    for message_id, data in messages:
                        await process_message(agent, redis_client, message_id, data)

            except Exception as e:
                logger.error(f"Stream Loop Error: {e}")
                await asyncio.sleep(5)

    finally:
        await redis_client.close()
        logger.info("👷 Worker Shutting Down")


async def process_message(agent, redis_client, message_id, data):
    try:
        payload_json = data.get("payload")
        if not payload_json:
            await redis_client.xack(
                env_config.redis_stream_key, env_config.redis_group_name, message_id
            )
            return

        input_data = json.loads(payload_json)
        logger.info(f"Processing for User: {input_data.get('user_id')}")

        # --- RUN AGENT ---
        result = await agent.run(input_data)

        # 2. Log Result
        logger.info("--------- AGENT DECISION ---------")
        logger.info(f"Action:    {result.get('action')}")
        logger.info(f"Details:   {result.get('order_details')}")
        logger.info(f"Should Execute:   {result.get('should_execute')}")
        logger.info(f"Reasoning: {result.get('reasoning')}")
        logger.info("----------------------------------")

        # Acknowledge successful processing of the message in the Redis stream
        await redis_client.xack(
            env_config.redis_stream_key, env_config.redis_group_name, message_id
        )

    except Exception as e:
        logger.error(f"Message Error {message_id}: {e}")
