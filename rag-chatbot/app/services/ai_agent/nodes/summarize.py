from typing import Any, Dict

from langchain_core.messages import RemoveMessage, SystemMessage

from app.services.ai_agent.state import AgentState
from app.utils.logger import setup_logging

logger = setup_logging()


async def summarize_node(state: AgentState, llm: Any) -> Dict[str, Any]:
    """
    Summarizes the chat history if it exceeds a threshold (e.g., 6 messages).
    Removes the old messages while maintaining a rolling summary.
    """
    messages = state.get("messages", [])
    current_summary = state.get("summary", "")

    # Threshold for summarization (6 messages total: ~3 turns of user/assistant)
    # We keep the last 2 messages for immediate conversation context
    threshold = 6

    if len(messages) <= threshold:
        return {}

    logger.info(f"Summarizing {len(messages)} messages (Threshold: {threshold}).")

    # Construct the summarization prompt
    summary_instruction = (
        "Summarize the following conversation in a concise manner (1-2 sentences). "
        "Include key entities mentioned and the current state of the request. "
        "Maintain continuity with any previous summary provided."
    )

    if current_summary:
        summary_instruction += f"\n\nPrevious summary: {current_summary}"

    summarization_query = [
        SystemMessage(content=summary_instruction),
        *messages[:-2],  # Summarize everything EXCEPT the last 2 messages
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
