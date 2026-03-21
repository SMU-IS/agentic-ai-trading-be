from typing import Any, Dict

from langchain_core.messages import HumanMessage, SystemMessage

from app.services.ai_agent.state import AgentState
from app.utils.logger import setup_logging

logger = setup_logging()


async def llm_chat_node(
    state: AgentState, llm: Any, system_prompt: str
) -> Dict[str, Any]:
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=state.get("query", "")),
    ]
    response = await llm.ainvoke(messages)
    return {"messages": [response]}
