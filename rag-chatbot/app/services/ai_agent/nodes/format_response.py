import json
from typing import Any, Dict

from app.services.ai_agent.state import AgentState
from app.utils.logger import setup_logging

logger = setup_logging()


def format_response_node(state: AgentState) -> Dict[str, Any]:
    """Cleans up JSON strings into human-readable text before finishing."""
    messages = state.get("messages", [])
    if not messages:
        return {}

    last = messages[-1]
    content = str(getattr(last, "content", last))
    formatted = content

    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            if "context" in parsed:
                formatted = parsed["context"]
            elif "ticker" in parsed:
                formatted = (
                    f"Order ID: {state.get('order_id', 'N/A')}\n"
                    f"Ticker: {parsed.get('ticker', 'N/A')}\n"
                    f"Action: {parsed.get('action', 'N/A')}\n"
                    f"Reasoning: {parsed.get('reasoning', 'N/A')}"
                )
    except (json.JSONDecodeError, ValueError):
        pass

    if formatted == content:
        return {}

    # Replace the last message by using the same ID
    new_msg = last.__class__(content=formatted, id=getattr(last, "id", None))
    return {"messages": [new_msg]}
