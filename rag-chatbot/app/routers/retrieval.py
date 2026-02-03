from functools import lru_cache

from app.core.config import env_config
from app.core.constant import APIPath
from app.providers.llm.registry import get_strategy
from app.schemas.chat import ChatRequest
from app.services.retrieval_service import RetrievalService
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

router = APIRouter(tags=["RAG Chatbot"])


@lru_cache()
def get_retrieval_service():
    strategy = get_strategy(env_config.llm_provider)
    llm_model = strategy.create_model()
    retrieval_service = RetrievalService(llm_model)

    return retrieval_service


# general query


# query + order_id
@router.post(APIPath.ORDER)
async def chat_stream(
    request: ChatRequest,
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
):
    return StreamingResponse(
        retrieval_service.fetch_order_details_augment_response(
            query=request.query, order_id=request.order_id
        ),
        media_type="text/event-stream",
    )
