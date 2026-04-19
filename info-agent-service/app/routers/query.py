import json
from functools import lru_cache
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.schemas.chat import ChatHistoryItem, ChatHistoryResponse, ChatRequest
from app.services.info_agent import InfoAgentService

router = APIRouter(tags=["Chat"])


@lru_cache()
def get_info_agent_service():
    return InfoAgentService()


@router.post("/query")
async def chat(
    request: ChatRequest, service: InfoAgentService = Depends(get_info_agent_service)
):
    async def event_generator() -> AsyncGenerator:
        try:
            async for chunk in service.ainvoke(
                question=request.query,
                session_id=request.session_id,
            ):
                if chunk:
                    yield chunk
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/history/{session_id}", response_model=ChatHistoryResponse)
async def get_history(
    session_id: str, service: InfoAgentService = Depends(get_info_agent_service)
):
    try:
        history = service.get_session_history(session_id)
        messages = history.messages
        formatted_history = []
        for msg in messages:
            role = "user" if msg.type == "human" else "assistant"
            formatted_history.append(ChatHistoryItem(role=role, content=msg.content))
        return ChatHistoryResponse(history=formatted_history)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/history/{session_id}")
async def clear_history(
    session_id: str, service: InfoAgentService = Depends(get_info_agent_service)
):
    try:
        service.clear_session_history(session_id)
        return {"status": "success", "message": f"History for {session_id} cleared"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
