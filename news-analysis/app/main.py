import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter

from app.core.constant import APIPath
from app.routers import query_docs
from app.services.orchestration import run_pipeline


def separate_worker_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_pipeline())
    loop.close()


async def news_worker():
    print("⏳ Worker waiting for server startup...")
    await asyncio.sleep(10)
    print("👷🏻‍♂️ News Analysis Worker loop started")

    while True:
        try:
            await run_pipeline()

            await asyncio.sleep(1)

        except Exception as e:
            print(f"❌ Worker Error: {e}")
            await asyncio.sleep(5)


# async def news_worker():
#     print("⏳ Worker waiting for server startup...")
#     await asyncio.sleep(60)
#     print("👷🏻‍♂️ News Analysis Worker started")
#     print("👷🏻‍♂️ Running pipeline in a separate thread...")
#     loop = asyncio.get_running_loop()
#     await loop.run_in_executor(None, separate_worker_thread)


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
