import os
from functools import partial
from typing import Literal, cast

from langchain_core.messages import SystemMessage
from langgraph.graph import END, StateGraph

from app.schemas.router_decision import RouterDecision
from app.services.ai_agent.nodes import (
    extract_order_id_node,
    format_response_node,
    general_news_node,
    llm_chat_node,
    should_summarise,
    summarise_node,
    trade_history_node,
)
from app.services.ai_agent.state import AgentState
from app.utils.logger import setup_logging

logger = setup_logging()


class ChatWorkflow:
    def __init__(self, llm, tools, system_prompt, checkpointer=None):
        self.llm = llm
        self.tools = tools
        self.system_prompt = system_prompt
        self.checkpointer = checkpointer
        self.graph = self._build()

    async def _route(
        self, state: AgentState
    ) -> Literal["trade_history", "general_news", "llm_chat"]:

        structured_llm = self.llm.with_structured_output(RouterDecision)
        current_order = state.get("order_id", "None")

        routing_instructions = (
            "You are a sophisticated routing assistant for a trading app.\n"
            f"ACTIVE CONTEXT: The user is currently discussing Order ID: {current_order}.\n\n"
            "INSTRUCTIONS:\n"
            "1. If the user asks a follow-up question related to this order (e.g., 'status?', 'when?', 'details'), "
            "route to 'trade_history'.\n"
            "2. If they ask about a NEW order ID, route to 'trade_history'.\n"
            "3. If they ask about market trends or news, route to 'general_news'.\n"
            "4. Otherwise, route to 'llm_chat'.\n"
            "Return the 'next_node' and your 'reasoning'."
        )

        try:
            decision = await structured_llm.ainvoke(
                [
                    SystemMessage(content=routing_instructions),
                    *state["messages"][-3:],
                ]
            )

            logger.info(
                f"LLM-First Route: {decision.next_node} | Reason: {decision.reasoning}"
            )
            return decision.next_node

        except Exception as e:
            logger.warning(f"Routing failed: {e}. Defaulting to llm_chat.")
            return "llm_chat"

    def _build(self):
        graph = StateGraph(AgentState)

        bound_chat_node = partial(
            llm_chat_node, llm=self.llm, system_prompt=self.system_prompt
        )
        bound_summarise_node = partial(summarise_node, llm=self.llm)

        # 1. Add Nodes
        graph.add_node("extract_order_id", extract_order_id_node)
        graph.add_node("trade_history", trade_history_node)
        graph.add_node("general_news", general_news_node)
        graph.add_node("llm_chat", bound_chat_node)
        graph.add_node("format_response", format_response_node)
        graph.add_node("summarise", bound_summarise_node)

        # 2. Set Entry Point
        graph.set_entry_point("extract_order_id")

        # 3. Define Conditional Routing from Entry
        graph.add_conditional_edges(
            "extract_order_id",
            self._route,
            {
                "trade_history": "trade_history",
                "general_news": "general_news",
                "llm_chat": "llm_chat",
            },
        )

        # 4. Route all processing nodes to the Formatter
        graph.add_edge("trade_history", "format_response")
        graph.add_edge("general_news", "format_response")
        graph.add_edge("llm_chat", "format_response")

        # 5. Conditional logic: Decide whether to Summarise or End
        graph.add_conditional_edges(
            "format_response",
            should_summarise,  # This function returns "summarise" or "end"
            {"summarise": "summarise", "end": END},
        )

        # 6. After summarizing, the flow ends
        graph.add_edge("summarise", END)

        return graph.compile(checkpointer=self.checkpointer)

    async def ainvoke(self, state: AgentState, config: dict) -> AgentState:
        result = await self.graph.ainvoke(state, config=config)
        return cast(AgentState, result)

    def export_graph(self):
        """Saves a visual representation of the workflow."""

        try:
            folder_name = "public"
            os.makedirs(folder_name, exist_ok=True)
            filepath = os.path.join(folder_name, "chat-workflow.png")

            graph_image = self.graph.get_graph().draw_mermaid_png()
            if graph_image:
                with open(filepath, "wb") as f:
                    f.write(graph_image)
                logger.info(f"Graph saved to {os.path.abspath(filepath)}")
            else:
                logger.warning(
                    "Graph image is empty - mermaid generation may have failed"
                )
        except Exception as e:
            logger.error(f"Failed to export graph: {e}", exc_info=True)


if __name__ == "__main__":
    graph = ChatWorkflow(llm=None, tools=[], system_prompt="")
    graph.export_graph()
