from pydantic import BaseModel, Field
from typing import List, Optional


class ChatRequest(BaseModel):
    query: str
    session_id: str


class ChatResponse(BaseModel):
    response: str


class ChatHistoryItem(BaseModel):
    role: str
    content: str


class ChatHistoryResponse(BaseModel):
    history: List[ChatHistoryItem]
