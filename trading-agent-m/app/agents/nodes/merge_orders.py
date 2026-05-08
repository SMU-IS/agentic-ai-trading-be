from app.agents.state import AgentState


async def node_merge_orders(state: AgentState) -> AgentState:
    """
    Fan-in node. Waits for both risk_adjust and profile_reasoning to complete,
    then combines their order lists into a single order_list for execute.
    """
    order_list         = state.get("standard_order_list") or []
    profile_order_list = state.get("profile_order_list") or []

    combined = [*order_list, *profile_order_list]

    should_execute = any(r.get("should_execute", False) for r in combined)

    print(f"   [🔀 Merge] standard={len(order_list)} | profile={len(profile_order_list)} | should_execute={should_execute}")

    return {
        "order_list":     combined,
        "should_execute": should_execute,
    }
