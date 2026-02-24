import json

from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres import PostgresSaver
from rich.console import Console
from rich.panel import Panel
from rich.pretty import Pretty

from app.core.config import env_config
from app.core.constant import LangChainEvent
from app.core.s3_config import S3ConfigService
from app.services.tools import RAG_BOT_TOOLS
from app.utils.logger import setup_logging

console = Console(force_terminal=True)

logger = setup_logging()


class AgentBotService:
    def __init__(self, llm: BaseChatModel, checkpointer: PostgresSaver):
        self.llm: BaseChatModel = llm
        self.checkpointer = checkpointer

        self.aws_config: S3ConfigService = S3ConfigService()
        self.aws_s3_bucket_name: str = env_config.aws_bucket_name
        self.aws_s3_file_name: str = env_config.aws_file_name

        self._prompt_cache = None

    def _get_llm_prompt(self) -> str:
        """
        Fetches the prompt from S3 and caches it.

        Returns:
            str: The prompt.
        """
        if self._prompt_cache:
            return self._prompt_cache

        try:
            logger.info(f"Fetching fresh prompt from S3: {self.aws_s3_file_name}")
            content = self.aws_config.get_file_content(
                self.aws_s3_bucket_name, self.aws_s3_file_name
            )
            self._prompt_cache = content
            return content

        except Exception as e:
            logger.exception(f"Failed to load prompt from S3 {e}")
            raise

    def _create_agent(self):
        """
        Create an agent with the given LLM and tools.

        Returns:
            Agent: The created agent.
        """
        prompt = self._get_llm_prompt()
        summariser = SummarizationMiddleware(
            model=self.llm,
            trigger=("messages", 20),
            keep=("messages", 5),
        )

        agent = create_agent(
            model=self.llm,
            tools=RAG_BOT_TOOLS,
            checkpointer=self.checkpointer,
            middleware=[summariser],
            system_prompt=prompt,
        )

        return agent

    async def invoke_agent(self, query: str, order_id: str | None, session_id: str):
        """
        Invoke the agent with a given query.

        Args:
            query (str): The query to invoke the agent with.
            order_id (str | None): The order ID for the query.

        Returns:
            str: The result of the agent invocation.
        """

        config = {"configurable": {"thread_id": session_id}}
        context_query = f"Regarding Order Id {order_id}: {query}" if order_id else query

        try:
            agent = self._create_agent()
            logger.info(f"Invoking agent with query: {context_query[:50]}...")

            results = agent.astream_events(
                {"messages": [HumanMessage(content=context_query)]},
                version="v2",
                config=config,
            )

            async for event in results:
                kind = event["event"]
                if kind == LangChainEvent.TOOL_START:
                    yield f"data: {json.dumps({'status': f'Calling {event['name']}...'})}\n\n"

                elif kind == LangChainEvent.CHAT_MODEL_STREAM:
                    content = event["data"]["chunk"].content  # type: ignore
                    if content:
                        yield f"data: {json.dumps({'token': content})}\n\n"

                if kind == LangChainEvent.CHAT_MODEL_END_STREAM:
                    output = event["data"]["output"]
                    console.print(
                        Panel(
                            Pretty(output),
                            title="🧠 Thinking...",
                            border_style="red",
                        )
                    )

        except Exception as e:
            logger.error(f"Streaming Error: {str(e)}", exc_info=True)
            error_msg = json.dumps({"error": f"An error occurred: {str(e)}"})
            yield f"data: {error_msg}\n\n"

        finally:
            yield "data: [DONE]\n\n"
