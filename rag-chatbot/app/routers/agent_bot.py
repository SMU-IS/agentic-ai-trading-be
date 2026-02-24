from functools import lru_cache

from app.core.config import env_config
from app.core.constant import APIPath
from app.providers.llm.registry import get_strategy
from app.schemas.chat import ChatRequest
from app.services.agent_bot_service import AgentBotService
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

router = APIRouter(tags=["RAG Chatbot"])


@lru_cache()
def get_agent_bot_service(request: Request):
    strategy = get_strategy(env_config.llm_provider)
    llm_model = strategy.create_model()
    return AgentBotService(llm_model, checkpointer=request.app.state.checkpointer)


@router.post(APIPath.CHAT)
async def chat_stream(
    chat_data: ChatRequest,
    agent_bot_service: AgentBotService = Depends(get_agent_bot_service),
):
    return StreamingResponse(
        agent_bot_service.invoke_agent(
            chat_data.query, chat_data.order_id, session_id=chat_data.session_id
        ),
        media_type="text/event-stream",
    )
