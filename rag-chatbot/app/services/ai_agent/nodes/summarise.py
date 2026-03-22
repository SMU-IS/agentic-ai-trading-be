from typing import Any, Dict, Literal

from langchain_core.messages import RemoveMessage, SystemMessage

from app.services.ai_agent.state import AgentState
from app.utils.logger import setup_logging

logger = setup_logging()


def should_summarise(state: AgentState) -> Literal["summarise", "end"]:
    if len(state.get("messages", [])) > 20:
        return "summarise"
    return "end"


async def summarise_node(state: AgentState, llm: Any) -> Dict[str, Any]:
    """
    Summarises the chat history if it exceeds a threshold (e.g., 20 messages).
    Removes the old messages while maintaining a rolling summary.
    """
    messages = state.get("messages", [])
    current_summary = state.get("summary", "")

    # Threshold for summarization (20 messages total: ~10 turns of user/assistant)
    # We keep the last 2 messages for immediate conversation context
    threshold = 20

    if len(messages) <= threshold:
        return {}

    logger.info(f"Summarising {len(messages)} messages (Threshold: {threshold}).")

    # Construct the summarisation prompt
    summary_instruction = (
        "Summarise the following conversation in a concise manner (1-2 sentences). "
        "Include key entities mentioned and the current state of the request. "
        "Maintain continuity with any previous summary provided."
    )

    if current_summary:
        summary_instruction += f"\n\nPrevious summary: {current_summary}"

    summarization_query = [
        SystemMessage(content=summary_instruction),
        *messages[:-2],  # Summarise everything EXCEPT the last 2 messages
    ]

    try:
        response = await llm.ainvoke(summarization_query)
        new_summary = response.content

        delete_messages = [
            RemoveMessage(id=m.id) for m in messages[:-2] if hasattr(m, "id") and m.id
        ]

        logger.info(f"Generated new summary: {new_summary[:50]}...")

        return {"summary": new_summary, "messages": delete_messages}

    except Exception as e:
        logger.error(f"Summarization failed: {e}")
        return {}
