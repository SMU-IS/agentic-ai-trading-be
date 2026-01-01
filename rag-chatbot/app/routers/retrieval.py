from functools import lru_cache

from app.core.config import env_config
from app.core.constant import APIPath
from app.core.security import get_current_user
from app.providers.llm.registry import get_strategy
from app.providers.vector.registry import get_vector_strategy
from app.schemas.chat import ChatRequest
from app.services.retrieval_service import RetrievalService
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

router = APIRouter(tags=["RAG Chatbot"], dependencies=[Depends(get_current_user)])


@lru_cache()
def get_retrieval_service() -> RetrievalService:
    strategy = get_strategy(env_config.llm_provider)
    llm_model = strategy.create_model()

    vector_strategy = get_vector_strategy(env_config.storage_provider)
    vector_store_instance = vector_strategy.get_vector_store()

    retrieval_service = RetrievalService(llm_model, vector_store_instance)

    return retrieval_service


@router.post(APIPath.CHAT)
async def chat_stream(
    request: ChatRequest,
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
):
    return StreamingResponse(
        retrieval_service.generate_response(request.message),
        media_type="text/event-stream",
    )
