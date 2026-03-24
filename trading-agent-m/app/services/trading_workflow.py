import os
from functools import partial

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.agents.nodes import (
    node_decide_trade,
    node_execute_trade,
    node_fetch_market_data,
    node_risk_adjust_trade,
    node_trade_logging,
    node_fetch_signal_data
)
from app.agents.state import AgentState, RiskProfile


class TradingWorkflow:
    def __init__(self, llm_client, redis_service):
        self.llm = llm_client
        self.redis_service = redis_service
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(AgentState)

        reasoning_with_llm = partial(node_decide_trade, self.llm)
        node_trade_logging_with_redis = partial(node_trade_logging, self.redis_service)


        # 1. Nodes
        graph.add_node("lookup_context", node_fetch_signal_data)
        graph.add_node("fetch_market_data", node_fetch_market_data)
        graph.add_node("reasoning", reasoning_with_llm)
        graph.add_node("node_risk_adjust_trade", node_risk_adjust_trade)
        graph.add_node("execute", node_execute_trade)
        graph.add_node("trade_logging", node_trade_logging_with_redis)

        # 2. Edges
        graph.add_edge(START, "lookup_context")
        graph.add_edge("lookup_context", "fetch_market_data")
        graph.add_edge("fetch_market_data", "reasoning")
        graph.add_edge("execute", "trade_logging")

        # # Conditional: Only trade if the brain says so
        graph.add_conditional_edges(
            "reasoning",
            self.edge_has_trade_opportunity,
            {True: "node_risk_adjust_trade", False: "trade_logging"},
        )

        graph.add_conditional_edges(
            "node_risk_adjust_trade",
            self.edge_should_execute,
            {True: "execute", False: "trade_logging"},
        )

        graph.add_edge("trade_logging",       END)
        return graph.compile()

    # ###### Edge Logic ######
    def edge_should_execute(self, state: AgentState):
        return state.get("should_execute", False)

    def edge_has_trade_opportunity(self, state: AgentState):
        return state.get("has_trade_opportunity", False)

    # ###### Public Runner ######
    async def run(self, input_data: dict):
        result = await self.graph.ainvoke(input_data)
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
