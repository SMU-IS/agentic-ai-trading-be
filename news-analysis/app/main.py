import asyncio
import json
import logging
from contextlib import asynccontextmanager

# from app.services.pipeline import run_pipeline # TODO: Add this once done
import redis.asyncio as redis  # type: ignore
from fastapi import FastAPI
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter

from app.core.config import env_config
from app.core.constant import APIPath
from app.routers import query_docs


async def news_worker():
    """
    Continuous loop that consumes from the 'Raw News Queue' (Redis)
    """

    r = redis.from_url(env_config.redis_url, decode_responses=True)
    queue_name = env_config.redis_news_queue

    print(f"[*] News Analysis Worker started. Listening on '{queue_name}'...")

    while True:
        try:
            result = await r.brpop(queue_name, timeout=0)

            if result:
                _, message = result
                news_item = json.loads(message)

                # Execute the full 5-step pipeline (01_preprocesser -> 05_vectorisation)
                # await run_pipeline(news_item) # TODO: Add this once done

        except Exception as e:
            print(f"[!] Worker Error: {e}")
            await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    worker_task = asyncio.create_task(news_worker())
    yield
    worker_task.cancel()


app = FastAPI(
    title="News Analysis Service",
    description="Processes raw news through a 5-step pipeline and stores in Qdrant",
    lifespan=lifespan,
    contact={
        "name": "SMU IS484 - Mvidia",
        "url": "https://github.com/SMU-IS/agentic-ai-trading-be",
    },
    root_path="/api/v1/news-analysis",
)


logger = logging.getLogger("uvicorn.error")
api_router = APIRouter()


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Internal Server Error at {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An internal server error occurred. Please try again later."
        },
    )


@app.get(APIPath.HEALTH_CHECK)
def health_check():
    return {"status": "News Analysis Service is healthy"}


# ====== API Endpoints ======
api_router.include_router(query_docs.router)
app.include_router(api_router)
