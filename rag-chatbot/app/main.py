from fastapi.applications import FastAPI
from fastapi.routing import APIRouter

from app.core.config import env_config
from app.core.constant import APIPath
from app.routers import chat, ingestion

app = FastAPI(
    title="Agentic AI Trading Portfolio Backend",
    description="",
    contact={
        "name": "SMU IS484 - Mvidia",
        "url": "https://github.com/SMU-IS/agentic-ai-trading-be",
    },
)
api_v1_router = APIRouter(prefix=env_config.api_version)


@app.get(APIPath.HEALTH_CHECK, tags=["Healthcheck"])
def root():
    return {"status": "RAG Chatbot Service is healthy"}


# ====== API Endpoints ======
api_v1_router.include_router(ingestion.router)
api_v1_router.include_router(chat.router)

app.include_router(api_v1_router)
