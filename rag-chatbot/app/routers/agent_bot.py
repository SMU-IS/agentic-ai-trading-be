from functools import lru_cache

from app.core.config import env_config
from app.core.constant import APIPath
from app.providers.llm.registry import get_strategy
from app.schemas.chat import ChatRequest
from app.services.agent_bot_service import AgentBotService
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

router = APIRouter(tags=["RAG Chatbot"])


@lru_cache()
def get_agent_bot_service():
    strategy = get_strategy(env_config.llm_provider)
    llm_model = strategy.create_model()
    agent_bot_service = AgentBotService(llm_model)
    return agent_bot_service


@router.post(APIPath.CHAT)
async def chat_stream(
    request: ChatRequest,
    agent_bot_service: AgentBotService = Depends(get_agent_bot_service),
):
    return StreamingResponse(
        agent_bot_service.invoke_agent(request.query, request.order_id),
        media_type="text/event-stream",
    )
