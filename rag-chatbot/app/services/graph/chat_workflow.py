import os
from datetime import datetime
from typing import cast

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
)
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

        # Pre-bind tools once to avoid redundant processing and API validation conflicts
        self.llm_with_tools = self.llm.bind_tools(self.tools)

        self.graph = self._build()

    async def _summarize_conversation(self, state: AgentState):
        """
        Summarizes the conversation if it exceeds a certain length to stay within context limits.
        Instead of deleting messages (which removes history from UI), it updates the summary
        for context and tracks progress using last_summarized_id.
        """
        messages = state["messages"]
        summary = state.get("summary", "")
        last_summarized_id = state.get("last_summarized_id")

        # Thresholds for triggering summarization
        MESSAGE_COUNT_THRESHOLD = 12
        CHARACTER_LIMIT_THRESHOLD = 4000

        total_chars = sum(
            len(m.content)
            if hasattr(m, "content") and isinstance(m.content, str)
            else 0
            for m in messages
        )

        # We keep the last 6 messages as active context
        KEEP_COUNT = 6
        
        if (
            len(messages) <= MESSAGE_COUNT_THRESHOLD
            and total_chars < CHARACTER_LIMIT_THRESHOLD
        ):
            return {"summary": summary}

        # Identifying messages to summarize: everything after last_summarized_id up to messages[-KEEP_COUNT]
        start_idx = 0
        if last_summarized_id:
            for i, m in enumerate(messages):
                if getattr(m, "id", None) == last_summarized_id:
                    start_idx = i + 1
                    break
        
        # Messages to add to summary
        to_summarize = messages[start_idx : -KEEP_COUNT]
        
        # Optimization: Only summarize if we have a significant batch (e.g. 3+ messages)
        # OR if we are hitting high character counts overall
        if not to_summarize or (len(to_summarize) < 3 and total_chars < CHARACTER_LIMIT_THRESHOLD):
            return {"summary": summary}

        logger.info(
            f"Summarizing {len(to_summarize)} new messages into context"
        )

        if summary:
            # If the existing summary is already massive, we need to compress it rather than extend it.
            # 10,000 chars is roughly 2,500 tokens.
            if len(summary) > 10000:
                summary_message = (
                    f"This is a summary of the conversation to date: {summary}\n\n"
                    "The current summary is very long. Create a NEW, more condensed summary "
                    "that includes all key tool results and decisions from both the old summary "
                    "and these NEW messages above."
                    "\nSTRICT RULE: Output ONLY the summary text."
                )
            else:
                summary_message = (
                    f"This is a summary of the conversation to date: {summary}\n\n"
                    "Extend the summary by taking into account the NEW messages above.\n"
                    "CRITICAL: Record which tools were called and what their key results were."
                    "\nSTRICT RULE: Output ONLY the summary text."
                )
        else:
            summary_message = (
                "Create a concise summary of the conversation above.\n"
                "CRITICAL: Record which tools were called and what their key findings were."
                "\nSTRICT RULE: Output ONLY the summary text."
            )

        MAX_MSG_CHARS_FOR_SUMMARIZER = 2000

        try:
            # Clean and truncate messages for summarization
            clean_messages = []
            for m in to_summarize:
                content = getattr(m, "content", "")

                if not content and hasattr(m, "tool_calls") and m.tool_calls:
                    content = f"[AI executed action: {', '.join([tc.get('name', 'unknown') for tc in m.tool_calls])}]"

                if content:
                    truncated_content = content
                    if len(content) > MAX_MSG_CHARS_FOR_SUMMARIZER:
                        truncated_content = (
                            content[:MAX_MSG_CHARS_FOR_SUMMARIZER]
                            + "... [Truncated]"
                        )

                    if m.type == "human":
                        clean_messages.append(HumanMessage(content=truncated_content))
                    elif m.type == "ai":
                        clean_messages.append(AIMessage(content=truncated_content))
                    elif m.type == "tool":
                        clean_messages.append(
                            HumanMessage(content=f"Tool output: {truncated_content}")
                        )

            if not clean_messages:
                return {"summary": summary}

            response = await self.llm.ainvoke(
                clean_messages + [HumanMessage(content=summary_message)]
            )
            new_summary = response.content
            
            # Update the last summarized ID to the last message we just summarized
            new_last_id = getattr(to_summarize[-1], "id", last_summarized_id)
            
            return {"summary": new_summary, "last_summarized_id": new_last_id}

        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            return {"summary": summary}

    async def _call_model(self, state: AgentState, config: RunnableConfig):
        """
        Agent Node: Calls the LLM with the current message history and summary.
        Uses a sliding window for messages to stay within context limits while preserving full history in state.
        """
        messages = state["messages"]
        summary = state.get("summary", "")

        # Truncate messages for the LLM context if we have a summary
        # We start with the last 6 messages and expand backwards if we are in the middle of a tool call
        KEEP_COUNT = 6
        if summary and len(messages) > KEEP_COUNT:
            start_idx = len(messages) - KEEP_COUNT
            
            # 1. Ensure we don't start with a ToolMessage or a pending AI tool call
            while start_idx > 0 and (
                messages[start_idx].type == "tool" or 
                (messages[start_idx].type == "ai" and hasattr(messages[start_idx], "tool_calls") and messages[start_idx].tool_calls)
            ):
                start_idx -= 1
            
            # 2. Further ensure we include the most recent HumanMessage for context if it's nearby
            # This helps the LLM understand the current "active" user request.
            temp_idx = start_idx
            found_human = False
            # Look back up to 10 more messages for a HumanMessage
            # We want to make sure we don't orphan a chain of tool calls
            for i in range(temp_idx, max(-1, temp_idx - 10), -1):
                if messages[i].type == "human":
                    start_idx = i
                    found_human = True
                    break
            
            logger.info(f"Windowing: kept {len(messages) - start_idx} messages (Found Human: {found_human})")
            messages_to_send = messages[start_idx:]
        else:
            messages_to_send = messages

        # Inject dynamic context
        metadata = config.get("metadata", {})
        user_id = metadata.get("user_id", "Unknown")
        order_id = metadata.get("order_id")
        current_date = datetime.now().strftime("%A, %B %d, %Y")

        context_lines = [f"- Today's Date: {current_date}", f"- User ID: {user_id}"]
        if summary:
            context_lines.append(f"- COMPLETED ACTIONS & SUMMARY: {summary}")
        if order_id:
            context_lines.append(f"- Active Order Context: {order_id}")

        context_block = "\n".join(context_lines)

        # LOOP PREVENTION: Warn the agent if it's about to repeat its most recent action
        loop_prevention_msg = ""
        if len(messages) >= 2:
            last_msg = messages[-1]  # ToolMessage
            prev_msg = messages[-2]  # AIMessage with tool call
            if (
                last_msg.type == "tool"
                and prev_msg.type == "ai"
                and hasattr(prev_msg, "tool_calls")
                and prev_msg.tool_calls
            ):
                tool_name = prev_msg.tool_calls[0]["name"]
                loop_prevention_msg = (
                    f"\n\n### SYSTEM ADVISORY\n"
                    f"You just executed '{tool_name}' and received the data provided in the ToolMessage. "
                    "Analyze this data and provide your final response to the user. "
                    f"DO NOT call '{tool_name}' again with the same parameters. Move to the next step or conclude."
                )

        # DYNAMIC SYSTEM PROMPT: Simple and direct context injection to give LLM maximum control
        dynamic_system_prompt = (
            f"{self.system_prompt}\n\n"
            f"### CURRENT CONTEXT\n"
            f"- Today's Date: {current_date}\n"
            f"- User ID: {user_id}\n"
            f"{context_block}\n"
            f"{loop_prevention_msg}"
        )

        model = (
            self.llm_with_tools
            if self.llm_with_tools
            else self.llm.bind_tools(self.tools)
        )

        response = await model.ainvoke(
            [SystemMessage(content=dynamic_system_prompt)] + messages_to_send,
            config={"tags": ["user_response"]},
        )

        # Log metadata for debugging
        if response.response_metadata:
            logger.debug(f"LLM Response Metadata: {response.response_metadata}")
            if "failed_generation" in response.response_metadata:
                logger.error(
                    f"LLM Failed Generation: {response.response_metadata['failed_generation']}"
                )

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
