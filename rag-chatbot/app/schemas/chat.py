from pydantic import BaseModel
from pydantic.v1.fields import Field


class ChatRequest(BaseModel):
    query: str = Field(..., description="User query to the LLM")
    order_id: str | None = None
