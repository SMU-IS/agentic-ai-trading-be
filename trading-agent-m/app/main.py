import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from langchain_perplexity import (
    ChatPerplexity,  # Requires: pip install langchain-perplexity
)

from app.core.config import env_config
from app.services.redis_service import RedisService  # Your RedisService class
from app.services.trading_workflow import TradingWorkflow

redis_service: RedisService = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global redis_service, workflow, signal_task

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

    # Start signal processing task
    async def process_signals():
        async for signal in redis_service.listen_signal_stream():
            try:
                print(f"🚀 Processing signal: {signal.signal_id}")
                await workflow.run(signal)
            except Exception as e:
                print(f"❌ Workflow error for {signal.signal_id}: {e}")

    signal_task = asyncio.create_task(process_signals())

    yield
    # Shutdown
    signal_task.cancel()
    try:
        await signal_task
    except asyncio.CancelledError:
        pass
    await redis_service.close()


app = FastAPI(lifespan=lifespan)


@app.get("/healthcheck")
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
