import asyncio
import os
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from src.services.redis_service import RedisService
from src.workflows.main_workflow import setup_workflow

load_dotenv()

# Global state
redis_service: RedisService = None
workflow = None
stream_task = None


@asynccontextmanager
async def lifespan(app_: FastAPI):
    global redis_service, workflow, stream_task

    # Startup
    print("🚀 Starting services...")
    redis_service = RedisService()
    await redis_service.connect()
    workflow = await setup_workflow(redis_service)

    # ✅ Start stream processor DURING lifespan startup
    stream_task = asyncio.create_task(stream_processor())
    print(f"🚀 Services ready! App live on http://0.0.0.0:{os.getenv('PORT', 5008)}")

    yield

    # Shutdown
    print("🛑 Shutting down...")
    if stream_task:
        stream_task.cancel()
        try:
            await stream_task
        except asyncio.CancelledError:
            pass
    if redis_service:
        await redis_service.disconnect()
    print("🛑 Clean shutdown complete.")


app = FastAPI(lifespan=lifespan)


@app.get("/healthcheck")
async def health_check():
    """Fast health check endpoint."""
    return {
        "status": "healthy",
        "redis": redis_service is not None,
        "workflow": workflow is not None,
    }


async def stream_processor():
    """Background processor for Redis stream."""
    while True:  # Keep alive during app lifetime
        try:
            async for article in redis_service.listen_news_stream():
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


async def main():
    # ✅ NO stream_processor() here - lifespan handles it
    port = int(os.getenv("PORT", 5008))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
