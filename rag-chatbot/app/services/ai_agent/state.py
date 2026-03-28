"""Agent state definition for LangGraph-based AI agent."""

from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """
    State for the AI agent graph.

    Attributes:
        messages: List of messages in the conversation
        sender: Who sent the last message (e.g., "user", "agent")
        order_id: Extracted order ID from user query (if present)
        query: The original user query
        variables: Additional variables for node communication
        metadata: Metadata for the conversation (user_id, title, etc.)
    """

    messages: Annotated[list[BaseMessage], add_messages]
    sender: str
    order_id: str | None
    query: str
    summary: str | None
    variables: dict[str, Any] | None
    metadata: dict[str, str] | None
