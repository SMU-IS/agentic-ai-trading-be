import asyncio
from contextlib import asynccontextmanager
import httpx

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from langchain_perplexity import (
    ChatPerplexity,  # Requires: pip install langchain-perplexity
)

from app.core.config import env_config
from app.services.redis_service import RedisService  # Your RedisService class
from app.services.trading_workflow import TradingWorkflow

SERVICE_POLL_INTERVAL = 10  # seconds

redis_service: RedisService = None
service_enabled = asyncio.Event()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global redis_service, workflow, signal_task, poll_task

    # Init Redis
    redis_service = RedisService()
    await redis_service.connect()

    # Init Perplexity LLM + TradingWorkflow
    llm = ChatPerplexity(
        pplx_api_key=env_config.perplexity_api_key,
        model=env_config.perplexity_model or "llama-3.1-sonar-small-128k-online",
        temperature=env_config.perplexity_temperature or 0.2,
    )
    workflow = TradingWorkflow(llm_client=llm, redis_service=redis_service)

    # Seed initial state before starting tasks
    initial_enabled = await redis_service.get_service_enabled()
    status_str = "▶️  ENABLED" if initial_enabled else "⏸️  PAUSED"
    print(f"🔑 Service control key: {env_config.redis_service_control_key} → {status_str}")
    if initial_enabled:
        service_enabled.set()

    async def _is_market_open() -> bool:
        """Check Alpaca /clock — handles holidays and early closes automatically."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{env_config.trading_service_url}/clock")
                return resp.json().get("is_open", False)
        except Exception as e:
            print(f"⚠️  Market clock check failed: {e}")
            return False

    # Poll every SERVICE_POLL_INTERVAL seconds.
    # Both conditions must be True to run: Redis flag enabled AND market open.
    async def poll_service_control():
        while True:
            try:
                market_open = await _is_market_open()
                redis_enabled = await redis_service.get_service_enabled()
                should_run = market_open and redis_enabled

                if should_run and not service_enabled.is_set():
                    service_enabled.set()
                    print(f"▶️  Service ENABLED  — market_open={market_open} | redis_flag={redis_enabled}")
                elif not should_run and service_enabled.is_set():
                    service_enabled.clear()
                    print(f"⏸️  Service PAUSED   — market_open={market_open} | redis_flag={redis_enabled}")
            except Exception as e:
                print(f"⚠️  Service control poll error: {e}")
            await asyncio.sleep(SERVICE_POLL_INTERVAL)

    # Start signal processing task
    async def process_signals():
        async for signal, msg_id in redis_service.listen_signal_stream(service_enabled):
            try:
                print(f"🚀 Processing signal: {signal.signal_id}")
                await workflow.run(signal)
                await redis_service.ack_signal(msg_id)
            except Exception as e:
                print(f"❌ Workflow error for {signal.signal_id}: {e} — message stays in PEL for retry")

    poll_task = asyncio.create_task(poll_service_control())
    signal_task = asyncio.create_task(process_signals())

    yield
    # Shutdown
    poll_task.cancel()
    signal_task.cancel()
    for task in (poll_task, signal_task):
        try:
            await task
        except asyncio.CancelledError:
            pass
    await redis_service.close()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def health_check():
    """Health check endpoint - checks Redis connection"""
    try:
        if redis_service.redis is None:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "error", "message": "Redis not connected"},
            )

        # Ping Redis
        pong = await redis_service.redis.ping()
        stream_len = await redis_service.redis.xlen(redis_service.redis_signal_stream)

        return {
            "status": "healthy",
            "redis": {
                "connected": True,
                "ping": pong,
                "signal_stream_length": stream_len,
            },
        }
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "error", "message": str(e)},
        )
