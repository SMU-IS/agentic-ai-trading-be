from fastapi import FastAPI
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter

from app.routers import query
from app.utils.logger import setup_logging

logger = setup_logging()


app = FastAPI(
    title="Information Agent M",
    description="Service for answering questions about Agentic AI Trading app",
    contact={
        "name": "SMU IS484 - Mvidia",
        "url": "https://github.com/SMU-IS/agentic-ai-trading-be",
    },
    root_path="/api/v1/info-agent",
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
    return {"status": "Information Agent Service is healthy"}


# ====== API Endpoints ======
api_router.include_router(query.router)

app.include_router(api_router)
