from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter
from redis import Redis

from app.core.config import env_config
from app.core.constant import APIPath
from app.core.logger import logger
from app.routers import query_docs, vectorise_docs


redis_client = Redis(
    host=env_config.redis_host,
    port=env_config.redis_port,
    password=env_config.redis_password,
    decode_responses=True,
)

app = FastAPI(
    title="Qdrant Retrieval Service",
    description="Handles semantic search and document retrieval from Qdrant",
    contact={
        "name": "SMU IS484 - Mvidia",
        "url": "https://github.com/SMU-IS/agentic-ai-trading-be",
    },
    root_path="/api/v1/qdrant",
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


@app.get(APIPath.HEALTH_CHECK.value, tags=["Health Check"])
def health_check():
    try:
        # 1️⃣ Check Redis connection
        redis_client.ping()

        # 2️⃣ Scan for worker heartbeats
        cursor = 0
        pattern = "vectorisation:heartbeat:*"
        heartbeat_keys = []

        while True:
            cursor, keys = redis_client.scan(
                cursor=cursor,
                match=pattern,
                count=100,
            )
            heartbeat_keys.extend(keys)

            if cursor == 0:
                break

        # 3️⃣ Extract worker IDs
        active_workers = [
            key.replace("vectorisation:heartbeat:", "")
            for key in heartbeat_keys
        ]

        worker_alive = len(active_workers) > 0

        return {
            "status": "Qdrant Retrieval Service is healthy",
            "redis": True,
            "worker_alive": worker_alive,
            "active_workers": active_workers,
            "total_active_workers": len(active_workers),
        }

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "redis": False,
            "worker_alive": False,
        }

api_router.include_router(query_docs.router)
api_router.include_router(vectorise_docs.router)
app.include_router(api_router)