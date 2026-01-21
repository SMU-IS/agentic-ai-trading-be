import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from app.agents.graph import app_workflow
from app.workers.consumer import start_consumer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("API")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 API Starting up...")
    task = asyncio.create_task(start_consumer())

    yield

    logger.info("🛑 API Shutting down...")
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        logger.info("✅ Worker cancelled successfully")


app = FastAPI(lifespan=lifespan)
router = APIRouter()


@app.get("/healthcheck")
def health():
    return {"status": "Trading Agent M service is healthy"}


@router.post("/trading-agent")
async def run_agent(signal_data: dict):
    result = await app_workflow.run(signal_data)
    return result


"""
TODO: to be removed, for testing purpose only

docker exec -it redis-stream-consumer-enriched_market_signals redis-cli XADD enriched_market_signals "*" payload '{"user_id": "joshua_123", "ticker": "AAPL", "signal": {"sentiment": "bullish", "score": 0.95}, "portfolio": {"qty": 10, "avg_price": 150.0}, "risk_profile": "aggressive"}'
"""
