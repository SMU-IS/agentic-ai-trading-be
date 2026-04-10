import os
from datetime import datetime
from typing import cast

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.services.graph.state import AgentState
from app.utils.logger import setup_logging

logger = setup_logging()


class ChatWorkflow:
    def __init__(self, llm, tools, system_prompt, checkpointer=None):
        self.llm = llm
        self.tools = tools
        self.system_prompt = system_prompt
        self.checkpointer = checkpointer
        self.graph = self._build()

    async def _call_model(self, state: AgentState, config: RunnableConfig):
        """
        Agent Node: Calls the LLM with the current message history.
        """
        messages = state["messages"]

        # Inject dynamic context
        metadata = config.get("metadata", {})
        user_id = metadata.get("user_id", "Unknown")
        order_id = metadata.get("order_id")
        current_date = datetime.now().strftime("%A, %B %d, %Y")

        context_lines = [f"- Today's Date: {current_date}", f"- User ID: {user_id}"]
        if order_id:
            context_lines.append(f"- Active Order Context: {order_id}")

        dynamic_system_prompt = (
            f"{self.system_prompt}\n\nCurrent Context:\n" + "\n".join(context_lines)
        )

        llm_with_tools = self.llm.bind_tools(self.tools)

        response = await llm_with_tools.ainvoke(
            [SystemMessage(content=dynamic_system_prompt)] + messages,
            config={"tags": ["user_response"]},
        )

        return {"messages": [response]}

    def _build(self):
        # 1. Create the Graph
        workflow = StateGraph(AgentState)

        # 2. Add Nodes
        workflow.add_node("agent", self._call_model)
        workflow.add_node("tools", ToolNode(self.tools))

        # 3. Set Entry Point
        workflow.add_edge(START, "agent")

        # 4. Add Conditional Edges (The Cycle)
        workflow.add_conditional_edges(
            "agent",
            tools_condition,
        )

        # 5. Add edge from tools back to agent
        workflow.add_edge("tools", "agent")

        return workflow.compile(checkpointer=self.checkpointer)

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
    # For testing export
    from unittest.mock import MagicMock

    mock_llm = MagicMock()
    graph = ChatWorkflow(llm=mock_llm, tools=[], system_prompt="")
    graph.export_graph()
