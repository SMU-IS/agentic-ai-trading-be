import os
from functools import partial

from langgraph.graph import END, START, StateGraph

from app.agents.nodes import node_decide_trade, node_execute_trade, node_lookup_qdrant
from app.agents.state import AgentState


class TradingWorkflow:
    def __init__(self, llm_client, broker_client):
        self.llm = llm_client
        self.broker = broker_client
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(AgentState)

        reasoning_with_llm = partial(node_decide_trade, self.llm)
        execute_with_broker = partial(node_execute_trade, self.broker)

        # 1. Nodes
        graph.add_node("lookup_context", node_lookup_qdrant)
        graph.add_node("reasoning", reasoning_with_llm)
        graph.add_node("execute", execute_with_broker)

        # 2. Edges
        graph.add_edge(START, "lookup_context")
        graph.add_edge(
            "lookup_context", "reasoning"
        )  # TODO: use this once its completed
        # graph.add_edge(START, "reasoning")

        # Conditional: Only trade if the brain says so
        graph.add_conditional_edges(
            "reasoning", self.edge_should_execute, {True: "execute", False: END}
        )

        graph.add_edge("execute", END)

        return graph.compile()

    # ###### Edge Logic ######
    def edge_should_execute(self, state: AgentState):
        return state.get("should_execute", False)

    # ###### Public Runner ######
    async def run(self, input_data: dict):
        result = await self.graph.ainvoke(input_data)  # type: ignore
        return result

    def export_graph(self):
        folder_name = "public"
        if not os.path.exists(folder_name):
            os.makedirs(folder_name)

        filename = "agent-m-workflow.png"
        filepath = os.path.join(folder_name, filename)

        self.graph.get_graph().draw_mermaid()
        png_bytes = self.graph.get_graph().draw_mermaid_png()

        with open(filepath, "wb") as f:
            f.write(png_bytes)

        print(f"\nGraph saved to {os.path.abspath(filepath)}")
