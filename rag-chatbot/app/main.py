import logging

from fastapi.applications import FastAPI
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter

from app.core.constant import APIPath
from app.routers import chat, ingestion

logger = logging.getLogger("uvicorn.error")


app = FastAPI(
    title="Agentic AI Trading Portfolio Backend",
    description="",
    contact={
        "name": "SMU IS484 - Mvidia",
        "url": "https://github.com/SMU-IS/agentic-ai-trading-be",
    },
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


@app.get(APIPath.HEALTH_CHECK, tags=["Healthcheck"])
def root():
    return {"status": "RAG Chatbot Service is healthy"}


# ====== API Endpoints ======
api_router.include_router(ingestion.router)
api_router.include_router(chat.router)

app.include_router(api_router)
