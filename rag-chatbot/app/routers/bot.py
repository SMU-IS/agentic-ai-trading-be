from functools import lru_cache

from app.core.config import env_config
from app.core.constant import APIPath
from app.providers.llm.registry import get_strategy
from app.schemas.chat import ChatRequest
from app.services.bot import BotService
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

router = APIRouter(tags=["RAG Chatbot"])


@lru_cache()
def get_personalised_retrieval_service():
    strategy = get_strategy(env_config.llm_provider)
    llm_model = strategy.create_model()
    bot_service = BotService(llm_model)

    return bot_service


@router.post(APIPath.CHAT)
async def chat_stream(
    request: ChatRequest,
    bot_service: BotService = Depends(get_personalised_retrieval_service),
):
    return StreamingResponse(
        bot_service.fetch_order_details_augment_response(
            query=request.query, order_id=request.order_id
        ),
        media_type="text/event-stream",
    )
