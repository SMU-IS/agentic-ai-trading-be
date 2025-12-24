from app.core.constant import APIPath
from app.core.security import get_current_user
from app.schemas.chat import ChatRequest
from app.services.retrieval_service import RetrievalService
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

router = APIRouter(tags=["RAG Chatbot"], dependencies=[Depends(get_current_user)])
_retrieval_instance = RetrievalService()


def get_retrieval_service():
    return _retrieval_instance


@router.post(APIPath.CHAT)
async def chat_stream(
    request: ChatRequest,
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
):
    return StreamingResponse(
        retrieval_service.generate_response(request.message),
        media_type="text/event-stream",
    )
