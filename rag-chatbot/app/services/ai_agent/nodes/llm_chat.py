from typing import Any, Dict

from langchain_core.messages import SystemMessage

from app.services.ai_agent.state import AgentState
from app.utils.logger import setup_logging

logger = setup_logging()


async def llm_chat_node(
    state: AgentState, llm: Any, system_prompt: str
) -> Dict[str, Any]:
    summary = state.get("summary", "")
    if summary:
        # Prepend the summary as a SystemMessage to the conversation history
        system_prompt += f"\n\nCONTEXT SUMMARY: {summary}"

    messages = [
        SystemMessage(content=system_prompt),
        *state["messages"],
    ]
    response = await llm.ainvoke(messages)
    return {"messages": [response]}
