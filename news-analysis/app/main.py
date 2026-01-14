import logging
from fastapi import FastAPI
from fastapi.applications import FastAPI
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter
from fastapi.requests import Request
from app.routers import preprocess

logger = logging.getLogger("uvicorn.error")

app = FastAPI(
    title="Agentic AI Trading Portfolio Backend",
    description="",
    contact={
        "name": "SMU IS484 - Mvidia",
        "url": "https://github.com/SMU-IS/agentic-ai-trading-be",
    },
    root_path="/api/v1/analysis",
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

@app.get("/")
async def root():
    return {"message": "Hello World"}

api_router = APIRouter()

api_router.include_router(preprocess.router)

