from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter
from redis import Redis

from app.core.config import env_config
from app.core.constant import APIPath
from app.core.logger import logger

# ================= Redis (Health Only) =================
redis_client = Redis(
    host=env_config.redis_host,
    port=env_config.redis_port,
    password=env_config.redis_password,
    decode_responses=True,
)

app = FastAPI(
    title="Ticker Identification Service",
    description="API Service",
    root_path="/api/v1/ticker-identification",
)
api_router = APIRouter()


# ================= GLOBAL ERROR =================
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Internal Error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# ================= HEALTH CHECK =================
@app.get("/")
def health_check():
    try:
        redis_client.ping()

        # 🔎 Discover workers via heartbeat keys
        cursor = 0
        pattern = "tickeridentification:heartbeat:*"
        heartbeat_keys = []

        # Use SCAN (production safe)
        while True:
            cursor, keys = redis_client.scan(
                cursor=cursor,
                match=pattern,
                count=100,
            )
            heartbeat_keys.extend(keys)

            if cursor == 0:
                break

        # Extract worker IDs from key names
        active_workers = [
            key.replace("tickeridentification:heartbeat:", "") for key in heartbeat_keys
        ]

        return {
            "status": "healthy" if active_workers else "worker_unreachable",
            "redis": True,
            "active_workers": active_workers,
            "worker_alive": len(active_workers) > 0,
            "total_active_workers": len(active_workers),
        }

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "redis": False,
            "worker_alive": False,
        }


app.include_router(api_router)
