import os
from functools import partial

from langgraph.graph import END, START, StateGraph

from app.agents.nodes import node_decide_trade, node_execute_trade, node_lookup_qdrant, node_fetch_market_data, node_risk_adjust_trade, node_trade_logging
from app.agents.state import AgentState


class TradingWorkflow:
    def __init__(self, llm_client):
        self.llm = llm_client
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(AgentState)

        reasoning_with_llm = partial(node_decide_trade, self.llm)

        # 1. Nodes
        graph.add_node("lookup_context", node_lookup_qdrant)
        graph.add_node("fetch_market_data", node_fetch_market_data)
        graph.add_node("reasoning", reasoning_with_llm)
        graph.add_node("node_risk_adjust_trade", node_risk_adjust_trade)
        graph.add_node("execute", node_execute_trade)
        graph.add_node("trade_logging", node_trade_logging)

        # 2. Edges
        graph.add_edge(START, "lookup_context")
        graph.add_edge("lookup_context", "fetch_market_data")
        graph.add_edge("fetch_market_data", "reasoning")
        graph.add_edge("reasoning", "node_risk_adjust_trade")
        graph.add_edge("execute", "trade_logging")

        # Conditional: Only trade if the brain says so
        graph.add_conditional_edges(
            "reasoning", self.edge_has_trade_opportunity, {True: "node_risk_adjust_trade", False: END}
        )
        
        graph.add_conditional_edges(
            "node_risk_adjust_trade", self.edge_should_execute, {True: "execute", False: END}
        )


        return graph.compile()

    # ###### Edge Logic ######
    def edge_should_execute(self, state: AgentState):
        return state.get("should_execute", False)
    
    def edge_has_trade_opportunity(self, state: AgentState):
        return state.get("has_trade_opportunity", False)

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
