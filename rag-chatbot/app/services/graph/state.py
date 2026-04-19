"""Agent state definition for LangGraph-based AI agent."""

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """
    State for the AI agent graph.

    Attributes:
        messages: List of messages in the conversation.
                  Uses add_messages to append new messages to the history.
        summary: A summary of the conversation to date to handle context length.
        last_summarized_id: ID of the last message that was included in the summary.
    """

    messages: Annotated[list[BaseMessage], add_messages]
    summary: str
    last_summarized_id: str | None
