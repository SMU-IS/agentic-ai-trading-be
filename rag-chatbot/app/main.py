import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter

from app.core.db import db_manager
from app.routers import agent_bot, threads

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting up Agentic AI Bot Service...")
    async for checkpointer in db_manager.get_checkpointer():
        app.state.bot_memory = checkpointer
        logger.info("🤩 Application is ready to handle requests.")
        yield

    logger.info("🛑 Shutting down Agentic AI Service...")


app = FastAPI(
    lifespan=lifespan,
    title="Agentic AI Trading Portfolio Backend",
    description="",
    contact={
        "name": "SMU IS484 - Mvidia",
        "url": "https://github.com/SMU-IS/agentic-ai-trading-be",
    },
    root_path="/api/v1/rag",
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Internal Server Error at {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An internal server error occurred. Please try again later."
        },
    )


api_router = APIRouter()


@app.get("/", tags=["Healthcheck"])
def root():
    return {"status": "RAG Chatbot Service is healthy"}


# ====== API Endpoints ======
api_router.include_router(agent_bot.router)
api_router.include_router(threads.router)

app.include_router(api_router)
