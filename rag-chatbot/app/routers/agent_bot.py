from functools import lru_cache

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse

from app.core.config import env_config
from app.core.constant import APIPath
from app.providers.llm.registry import get_strategy
from app.schemas.chat import ChatHistoryResponse, ChatRequest
from app.services.agent_bot_service import AgentBotService
from app.utils.decode_jwt import get_current_user_id

router = APIRouter(tags=["RAG Chatbot"])


@lru_cache()
def get_agent_bot_service(request: Request):
    strategy = get_strategy(env_config.llm_provider)
    llm_model = strategy.create_model()
    return AgentBotService(llm_model, checkpointer=request.app.state.bot_memory)


@router.post(APIPath.CHAT)
async def chat_stream(
    chat_data: ChatRequest,
    user_id: str = Depends(get_current_user_id),
    agent_bot_service: AgentBotService = Depends(get_agent_bot_service),
):
    return StreamingResponse(
        agent_bot_service.invoke_agent(
            chat_data.query, chat_data.order_id, user_id, chat_data.session_id
        ),
        media_type="text/event-stream",
    )


@router.get(APIPath.CHAT_HISTORY, response_model=ChatHistoryResponse)
async def get_chat_history(
    session_id: str,
    agent_bot_service: AgentBotService = Depends(get_agent_bot_service),
):
    history = await agent_bot_service.get_chat_history(session_id)
    return ChatHistoryResponse(history=history)


@router.get(APIPath.USER)
def get_current_user(user_id: str = Depends(get_current_user_id)):
    if not user_id:
        return {"error": "User ID not found"}, 401

    return {"status": "success", "user_id": user_id}
