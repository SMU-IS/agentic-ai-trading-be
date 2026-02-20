from fastapi import FastAPI
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter

from app.core.constant import APIPath
from app.core.logger import logger
from app.routers import query_docs

app = FastAPI(
    title="Qdrant Retrieval Service",
    description="Handles semantic search and document retrieval from Qdrant",
    contact={
        "name": "SMU IS484 - Mvidia",
        "url": "https://github.com/SMU-IS/agentic-ai-trading-be",
    },
    root_path="/api/v1/qdrant-retrieval",
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
    return {"status": "Qdrant Retrieval Service is healthy"}


# ====== API Endpoints ======
api_router.include_router(query_docs.router)
app.include_router(api_router)
