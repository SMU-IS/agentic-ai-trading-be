import httpx
import asyncio
import os
from dotenv import load_dotenv
from typing import Dict, Any
from app.agents.state import AgentState
import json
# Load env vars
load_dotenv()

# Update your graph edge to return state
async def node_trade_logging(state: AgentState) -> AgentState:
    """Wrapper to mutate state."""
    # Log trade decision
    print("========================================")
    print("   [📝 Trade Logging] Current Agent State:")
    print("========================================")
    print(json.dumps(state, indent=2))
    print("========================================")
    print(
        f"   [📝 Trade Logging] Trade Decision: {state.get('order_details', {})} "
        f"| Execute: {state.get('should_execute', False)} "
        f"| Reason: {state.get('reasoning', '')}")
    
    return state
