import json

from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from app.core.constant import LangChainEvent
from app.core.prompts import TRADING_AGENT_PROMPT
from app.services.tools import RAG_BOT_TOOLS


class BotService:
    def __init__(self, llm: BaseChatModel):
        self.llm = llm
        self.tools = RAG_BOT_TOOLS
        self.agent_executor = self._build_agent_executor()

    def _build_agent_executor(self):
        """Builds the 'Brain' that decides between RAG and Tools."""
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", TRADING_AGENT_PROMPT),
                ("human", "{query}"),
                ("placeholder", "{agent_scratchpad}"),
            ]
        )

        agent = create_tool_calling_agent(self.llm, self.tools, prompt)
        return AgentExecutor(agent=agent, tools=self.tools)

    async def fetch_order_details_augment_response(
        self, query: str, order_id: str | None
    ):
        input_payload = {
            "query": f"User Query: {query} \n (Order ID Context: {order_id})",
        }

        citations = []

        try:
            async for event in self.agent_executor.astream_events(
                input_payload, version="v2"
            ):
                kind = event["event"]
                # 1. Detect when a tool is being called
                if kind == LangChainEvent.TOOL_START:
                    yield f"data: {json.dumps({'status': f'Calling {event['name']}...'})}\n\n"

                # 2. Detect when a tool has finished
                elif kind == LangChainEvent.TOOL_END:
                    output = event["data"].get("output")
                    if isinstance(output, dict) and "results" in output:
                        for result in output["results"]:
                            citations.append(
                                {
                                    "headline": result.get("headline"),
                                    "url": result.get("metadata", {}).get(
                                        "url", "No URL provided"
                                    ),
                                }
                            )

                # 2. Stream tokens, typing the final answer
                elif kind == LangChainEvent.CHAT_MODEL_STREAM:
                    content = event["data"]["chunk"].content
                    if content:
                        yield f"data: {json.dumps({'token': content})}\n\n"

            if citations:
                yield f"data: {json.dumps({'citations': citations})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            yield "data: [DONE]\n\n"
