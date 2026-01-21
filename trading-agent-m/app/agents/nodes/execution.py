from app.agents.state import AgentState


async def node_execute_trade(broker, state: AgentState):
    """
    Hands.
    To execute via Broker API.
    """

    print(
        f"!!! [🤝🏻 Market Access] Executing {state['action']} {state['order_details']}"
    )

    # TODO: Invoke brokerage API service

    return {}
