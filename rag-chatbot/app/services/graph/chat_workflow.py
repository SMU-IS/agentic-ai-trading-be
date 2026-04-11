import os
from datetime import datetime
from typing import cast

from langchain_core.messages import HumanMessage, RemoveMessage, SystemMessage, AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
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
        
        # Pre-bind tools to prevent redundant processing and potential API validation conflicts
        # during dynamic binding inside nodes.
        self.llm_with_tools = self.llm.bind_tools(self.tools)
        
        self.graph = self._build()

    async def _summarize_conversation(self, state: AgentState):
        """
        Summarizes the conversation if it exceeds a certain length to stay within context limits.
        """
        messages = state["messages"]
        summary = state.get("summary", "")

        # Thresholds for summarization
        MESSAGE_COUNT_THRESHOLD = 12
        CHARACTER_LIMIT_THRESHOLD = 4000 # Rough proxy for tokens

        total_chars = sum(
            len(m.content)
            if hasattr(m, "content") and isinstance(m.content, str)
            else 0
            for m in messages
        )

        if (
            len(messages) < MESSAGE_COUNT_THRESHOLD
            and total_chars < CHARACTER_LIMIT_THRESHOLD
        ):
            return {"summary": summary}

        logger.info(
            f"Summarizing conversation history ({len(messages)} messages, {total_chars} chars)"
        )

        if summary:
            summary_message = (
                f"This is a summary of the conversation to date: {summary}\n\n"
                "Extend the summary by taking into account the new messages above.\n"
                "STRICT RULE: Output ONLY the summary text. DO NOT attempt to call any tools or functions."
            )
        else:
            summary_message = (
                "Create a concise summary of the conversation above.\n"
                "STRICT RULE: Output ONLY the summary text. DO NOT attempt to call any tools or functions."
            )

        try:
            # Clean messages for summarization to avoid tool-call validation errors in Groq/Gemini.
            # We convert everything to simple Human/AI messages without tool_calls.
            clean_messages = []
            for m in messages:
                content = getattr(m, "content", "")
                if content:
                    if m.type == "human":
                        clean_messages.append(HumanMessage(content=content))
                    elif m.type == "ai":
                        clean_messages.append(AIMessage(content=content))
                    elif m.type == "tool":
                        # Convert tool output to something the summarizer can use as context
                        clean_messages.append(HumanMessage(content=f"Tool output: {content}"))
                
            if not clean_messages:
                return {"summary": summary}

            # Use the base (non-tool-bound) LLM for summarization
            response = await self.llm.ainvoke(
                clean_messages + [HumanMessage(content=summary_message)]
            )
            new_summary = response.content
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            new_summary = summary + " (Summarization failed, some history lost)"

        # Keep only the last 6 messages to preserve more context
        keep_count = 6
        delete_messages = [
            RemoveMessage(id=m.id)
            for m in messages[:-keep_count]
            if hasattr(m, "id") and m.id
        ]

        return {"summary": new_summary, "messages": delete_messages}

    async def _call_model(self, state: AgentState, config: RunnableConfig):
        """
        Agent Node: Calls the LLM with the current message history and summary.
        """
        messages = state["messages"]
        summary = state.get("summary", "")

        # Inject dynamic context
        metadata = config.get("metadata", {})
        user_id = metadata.get("user_id", "Unknown")
        order_id = metadata.get("order_id")
        current_date = datetime.now().strftime("%A, %B %d, %Y")

        context_lines = [f"- Today's Date: {current_date}", f"- User ID: {user_id}"]
        if summary:
            context_lines.append(f"- Previous Conversation Summary: {summary}")
        if order_id:
            context_lines.append(f"- Active Order Context: {order_id}")

        context_block = "\n".join(context_lines)

        dynamic_system_prompt = (
            f"{self.system_prompt}\n\n"
            f"### CURRENT SESSION CONTEXT\n{context_block}\n\n"
            "### RESPONSE GUIDELINES\n"
            "- If the user's request requires a tool, call the appropriate tool immediately.\n"
            "- Be concise and professional in your responses."
        )

        # Safety: Ensure tools are bound. In some environments/versions, 
        # RunnableBinding might lose its tools if not handled carefully.
        model = self.llm_with_tools
        if not hasattr(model, "kwargs") or "tools" not in model.kwargs:
             # Fallback: Re-bind tools if they somehow got dropped
             model = self.llm.bind_tools(self.tools)

        response = await model.ainvoke(
            [SystemMessage(content=dynamic_system_prompt)] + messages,
            config={"tags": ["user_response"]},
        )

        # Log metadata for debugging
        if response.response_metadata:
             logger.debug(f"LLM Response Metadata: {response.response_metadata}")
             if "failed_generation" in response.response_metadata:
                 logger.error(f"LLM Failed Generation: {response.response_metadata['failed_generation']}")

        return {"messages": [response]}

    def _build(self):
        workflow = StateGraph(AgentState)

        workflow.add_node("agent", self._call_model)
        workflow.add_node("summarize", self._summarize_conversation)
        workflow.add_node("tools", ToolNode(self.tools))

        workflow.add_edge(START, "summarize")
        workflow.add_edge("summarize", "agent")

        workflow.add_conditional_edges(
            "agent",
            tools_condition,
        )

        workflow.add_edge("tools", "summarize")

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
    from unittest.mock import MagicMock
    mock_llm = MagicMock()
    graph = ChatWorkflow(llm=mock_llm, tools=[], system_prompt="")
    graph.export_graph()
