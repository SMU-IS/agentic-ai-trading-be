import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.router.scraper import router as scraper_router
from app.services.scraper_controller import scraper_controller
from app.services.storage import get_redis_client

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("[*] Initialising app dependencies...")

    redis_client = get_redis_client()
    app.state.redis_client = redis_client

    logger.info("[*] App ready. Scraper starting.")
    await scraper_controller.start(app)

    yield

    logger.info("[*] Shutting down application...")


app = FastAPI(
    title="News Scraper Service (TradingView)",
    description="Scrapes TradingView Minds and Ideas for retail investor sentiment",
    lifespan=lifespan,
)

app.include_router(scraper_router)


@app.get("/")
def healthcheck():
    try:
        redis_client = get_redis_client()
        redis_client.ping()
        return {"status": "News Scraper (TradingView) Service is healthy"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "News Scraper (TradingView) Service is unhealthy"}
