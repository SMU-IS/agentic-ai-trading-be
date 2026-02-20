import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter

from app.core.constant import APIPath
from app.core.logger import logger
from app.services.orchestration import run_pipeline

# def separate_worker_thread():
#     loop = asyncio.new_event_loop()
#     asyncio.set_event_loop(loop)
#     loop.run_until_complete(run_pipeline())
#     loop.close()


async def news_worker():
    # r = Redis(
    #     host=env_config.redis_host,
    #     port=env_config.redis_port,
    #     password=env_config.redis_password,
    #     decode_responses=True,
    # )
    while True:
        try:
            logger.info("Running pipeline...")
            await run_pipeline()
        except Exception as e:
            logger.error(f"❌ Worker Error: {e}")
        finally:
            await asyncio.sleep(60)

    # while True:
    #     try:
    #         acquired = await r.set("pipeline_lock", "1", nx=True, ex=1800)
    #         if acquired:
    #             await run_pipeline()
    #             await r.delete("pipeline_lock")
    #         else:
    #             logger.info("⏭️ Another worker is running pipeline, skipping")
    #     except Exception as e:
    #         logger.error(f"❌ Worker Error: {e}")
    #     finally:
    #         await asyncio.sleep(60)


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
app.include_router(api_router)
