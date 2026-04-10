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
    """

    messages: Annotated[list[BaseMessage], add_messages]
