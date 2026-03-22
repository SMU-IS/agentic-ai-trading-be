import re
from typing import Any, Dict

from app.services.ai_agent.state import AgentState
from app.utils.logger import setup_logging

logger = setup_logging()


def extract_order_id_node(state: AgentState) -> Dict[str, Any]:
    messages = state.get("messages", [])
    content = str(getattr(messages[-1], "content", "")) if messages else ""
    existing_id = state.get("order_id")

    match = re.search(
        r"(?:transaction|symbol|id)[:\s]*([A-Z0-9.\-_]{2,})", content, re.IGNORECASE
    )

    new_id = None
    if match:
        candidate = match.group(1)
        blacklist = {
            "type",
            "date",
            "price",
            "quantity",
            "shares",
            "total",
            "value",
            "reason",
        }

        if candidate.lower() not in blacklist:
            new_id = candidate

    final_id = new_id if new_id else existing_id

    return {"query": content, "order_id": final_id}
