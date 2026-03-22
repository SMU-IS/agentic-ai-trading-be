from typing import Literal

from pydantic import BaseModel, Field


class RouterDecision(BaseModel):
    next_node: Literal["trade_history", "general_news", "llm_chat", "clarify"] = Field(
        description="The node to route to based on the query context. Use 'clarify' if uncertain or if order_id is needed but not provided."
    )
    reasoning: str = Field(description="Brief explanation for the routing choice.")
    confidence: float = Field(
        description="Confidence score between 0.0 and 1.0. Use 'clarify' if confidence is below 0.7."
    )
