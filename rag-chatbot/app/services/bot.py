import json

from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from app.core.config import env_config
from app.core.constant import LangChainEvent
from app.core.s3_config import S3ConfigService
from app.services.tools import RAG_BOT_TOOLS


class BotService:
    def __init__(self, llm: BaseChatModel):
        self.llm = llm
        self.tools = RAG_BOT_TOOLS

        self.aws_config = S3ConfigService()
        self.aws_s3_bucket_name = env_config.aws_bucket_name
        self.aws_s3_file_name = env_config.aws_file_name

        self.agent_executor = self._build_agent_executor()

    def _load_prompt_from_s3(self) -> str:
        try:
            return self.aws_config.get_file_content(
                self.aws_s3_bucket_name, self.aws_s3_file_name
            )
        except Exception as e:
            print(f"Error loading prompt from S3: {e}")
            raise

    def _build_agent_executor(self):
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", self._load_prompt_from_s3()),
                ("human", "Query: {query}\nOrder ID: {order_id}"),
                ("placeholder", "{agent_scratchpad}"),
            ]
        )

        agent = create_tool_calling_agent(self.llm, self.tools, prompt)
        return AgentExecutor(agent=agent, tools=self.tools)

    async def fetch_order_details_augment_response(
        self, query: str, order_id: str | None
    ):
        input_payload = {
            "query": query,
            "order_id": order_id if order_id else "Not Applicable",
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
                    if isinstance(output, dict) and output.get("results"):
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
                    chunk = event["data"]["chunk"]
                    if chunk.content and not chunk.tool_call_chunks:
                        yield f"data: {json.dumps({'token': chunk.content})}\n\n"

            if citations:
                yield f"data: {json.dumps({'citations': citations})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            yield "data: [DONE]\n\n"
