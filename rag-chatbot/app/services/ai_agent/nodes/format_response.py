from typing import Any, Dict

from langchain_core.messages import AIMessage, SystemMessage

from app.services.ai_agent.state import AgentState
from app.utils.logger import setup_logging

logger = setup_logging()


async def format_response_node(state: AgentState, llm) -> Dict[str, Any]:
    """Uses the LLM to turn raw data into a friendly, conversational response."""
    messages = state.get("messages", [])
    if not messages:
        return {}

    last_message = messages[-1]

    # If the last message is already an AI message, we don't need to format it again
    if isinstance(last_message, AIMessage):
        return {}

    prompt = (
        "You are a helpful, witty trading assistant. "
        "Take the following raw data and turn it into a natural, conversational response "
        "for the user. Don't just list facts—explain them like a friendly expert. "
        "Keep it concise but engaging."
    )

    response = await llm.ainvoke(
        [
            SystemMessage(content=prompt),
            *messages[-3:],
        ]
    )

    if last_message.id:
        response.id = last_message.id

    return {"messages": [response]}
