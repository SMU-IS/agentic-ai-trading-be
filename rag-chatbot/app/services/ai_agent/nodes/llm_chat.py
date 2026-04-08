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
        system_prompt += f"\n\nCONTEXT SUMMARY: {summary}"

    chat_instructions = (
        f"{system_prompt}\n\n"
        "ADDITIONAL INSTRUCTIONS:\n"
        "1. You are a witty, helpful trading assistant. "
        "2. Use the conversation history to answer questions about previous lists or trades. "
        "3. If the user asks 'is that all?' or 'why only 3?', look at the history to explain "
        "the context (e.g. 'Yes, those were the only Google trades I found for last week')."
    )

    messages = [
        SystemMessage(content=chat_instructions),
        *state["messages"],
    ]
    response = await llm.ainvoke(messages, config={"tags": ["user_response"]})
    return {"messages": [response]}
