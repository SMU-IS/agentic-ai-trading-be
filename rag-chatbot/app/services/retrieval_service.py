import json
import logging
from typing import AsyncGenerator

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_core.vectorstores import VectorStore

from app.core.constant import LangChainEvent


class RetrievalService:
    def __init__(self, llm: BaseChatModel, vector_store: VectorStore):
        # 1. Initialize LLM
        self.model = llm
        self.vector_store = vector_store

        # 2. Define the Tool
        @tool(response_format="content_and_artifact")
        def retrieve_context(query: str):
            """
            Retrieve additional context to help answer a query.
            """

            retrieved_docs = self.vector_store.similarity_search(query, k=2)

            serialized = "\n\n".join(
                (f"Source: {doc.metadata}\nContent: {doc.page_content}")
                for doc in retrieved_docs
            )
            return serialized, retrieved_docs

        self.tools = [retrieve_context]

        # 3. Create the Prompt
        self.system_prompt = (
            "You are a helpful assistant. To answer any question about AI or technical topics, "
            "you MUST use the 'retrieve_context' tool. "
            "Only use the tools provided in your toolset: [retrieve_context]. "
            "Once you receive the tool output, provide a final answer in 2-3 sentences. "
            "Start your final answer with '🚀 Final Answer:'"
        )

        self.agent_executor = create_agent(
            self.model, self.tools, system_prompt=self.system_prompt
        )

    async def generate_response(self, query: str) -> AsyncGenerator[str, None]:
        inputs = {"messages": [HumanMessage(content=query)]}

        try:
            async for event in self.agent_executor.astream_events(inputs, version="v2"):
                kind = event["event"]

                if kind == LangChainEvent.CHAT_MODEL_STREAM:
                    content = event["data"]["chunk"].content  # type: ignore
                    if content:
                        yield f"data: {json.dumps({'token': content})}\n\n"

                elif kind == LangChainEvent.TOOL_START:
                    yield f"data: {json.dumps({'status': 'searching_knowledge_base'})}\n\n"

        except Exception as e:
            logging.error(f"Error in RAG stream: {e}")
            yield f"data: {json.dumps({'error': 'Internal server error'})}\n\n"

        finally:
            yield "data: [DONE]\n\n"
