import asyncio
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from src.config import settings
from src.services.redis_service import RedisService
from src.workflows.main_workflow import setup_workflow


SERVICE_POLL_INTERVAL = 10  # seconds

# Global state
redis_service: RedisService = None
workflow = None
stream_task = None
poll_task = None
service_enabled = asyncio.Event()


@asynccontextmanager
async def lifespan(app_: FastAPI):
    global redis_service, workflow, stream_task, poll_task

    # Startup
    print("🚀 Starting services...")
    print("🔑 Loading config from .env...")
    print(f"🔑 Qdrant URL: {settings.news_analysis_qdrant_url}")
    print(f"🔑 Trading URL: {settings.aggregator_base_url}")
    print(f"🔑 LLM Provider: {settings.llm_provider}")
    print(f"🔑 Perplexity API Key: {settings.pplx_api_key[:4]}..." if settings.pplx_api_key else "None")
    print(f"🔑 Groq API Key: {settings.groq_api_key[:4]}..." if settings.groq_api_key else "None")
    print(f"🔑 Model: {settings.model}")

    print("🔑 Redis config:")
    print(f"  Host: {settings.redis_host}")
    print(f"  Port: {settings.redis_port}")
    print(f"  Password: {'*' * len(settings.redis_password)}")

    print()
    redis_service = RedisService()
    await redis_service.connect()
    workflow = await setup_workflow(redis_service)

    # Seed initial state
    initial_enabled = await redis_service.get_service_enabled()
    status_str = "▶️  ENABLED" if initial_enabled else "⏸️  PAUSED"
    print(f"🔑 Service control key: {settings.redis_service_control_key} → {status_str}")
    if initial_enabled:
        service_enabled.set()

    # Poll Redis every SERVICE_POLL_INTERVAL seconds to sync start/stop flag
    async def poll_service_control():
        while True:
            try:
                enabled = await redis_service.get_service_enabled()
                if enabled and not service_enabled.is_set():
                    service_enabled.set()
                    print(f"▶️  Service ENABLED  (key={settings.redis_service_control_key})")
                elif not enabled and service_enabled.is_set():
                    service_enabled.clear()
                    print(f"⏸️  Service PAUSED   (key={settings.redis_service_control_key})")
            except Exception as e:
                print(f"⚠️  Service control poll error: {e}")
            await asyncio.sleep(SERVICE_POLL_INTERVAL)

    poll_task = asyncio.create_task(poll_service_control())
    stream_task = asyncio.create_task(stream_processor())
    print(f"🚀 Services ready! App live on http://0.0.0.0:{os.getenv('PORT', 5008)}")

    yield

    # Shutdown
    print("🛑 Shutting down...")
    for task in (poll_task, stream_task):
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    if redis_service:
        await redis_service.disconnect()
    print("🛑 Clean shutdown complete.")


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def health_check():
    """Health check endpoint with dependency verification."""
    if redis_service is None:
        return {"status": "unhealthy", "reason": "redis_service not initialized"}

    try:
        # Test Redis connection
        await redis_service.redis.ping()
    except Exception as e:
        return {"status": "unhealthy", "reason": f"redis ping failed: {e}"}

    return {"status": "healthy"}


async def stream_processor():
    """Background processor for Redis stream."""
    while True:  # Keep alive during app lifetime
        try:
            async for article in redis_service.listen_news_stream(service_enabled):
                await workflow.run(
                    {
                        "articles": [article.to_dict()],
                        "qdrant_context": [],
                        "topics": [],
                        "triggered_topics": [],
                        "analyses": [],
                        "signals": [],
                    }
                )
        except Exception as e:
            print(f"Stream error: {e}, reconnecting...")
            await asyncio.sleep(5)
        # break
        # exit()


async def main():
    # ✅ NO stream_processor() here - lifespan handles it
    port = int(os.getenv("PORT", 5008))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
