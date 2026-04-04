from typing import Any, Dict

from langchain_core.messages import AIMessage

from app.services.ai_agent.state import AgentState
from app.utils.logger import setup_logging

logger = setup_logging()


def clarification_node(state: AgentState) -> Dict[str, Any]:
    """
    Node that asks the user for clarification when routing is uncertain.

    This node is triggered when the LLM router cannot confidently determine
    the user's intent. It prompts the user to provide more specific information.
    """
    query = state.get("query", "")

    clarification_prompt = (
        "I'm not fully sure about the details of your request. "
        "Could you please clarify:\n"
        "∙ If you're asking about a specific order, please provide the Order ID (e.g., 'Order 123' or 'transaction: ABC')\n"
        "∙ If you're asking about market news, please let me know which asset or sector you're interested in\n"
        "∙ If you have a general question, just let me know!"
    )

    clarification_message = AIMessage(content=clarification_prompt)
    logger.info(f"Clarification requested for query: {query}")

    # Ensure variables is not None
    variables = state.get("variables") or {}

    return {
        "messages": [clarification_message],
        "variables": variables | {"requires_clarification": True},
    }
