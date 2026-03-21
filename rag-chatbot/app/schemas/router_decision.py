from typing import Literal

from pydantic import BaseModel, Field


class RouterDecision(BaseModel):
    next_node: Literal["trade_history", "general_news", "llm_chat"] = Field(
        description="The node to route to based on the query context."
    )
    reasoning: str = Field(description="Brief explanation for the routing choice.")
