import json

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from rich.console import Console
from rich.panel import Panel
from rich.pretty import Pretty

from app.core.config import env_config
from app.core.constant import RedisCacheKeys
from app.core.s3_config import S3ConfigService
from app.schemas.chat import ChatHistoryResponse
from app.services.ai_agent import AgentState, ChatWorkflow
from app.services.bot_memory import BotMemory
from app.services.redis_service import RedisService
from app.services.tools import RAG_BOT_TOOLS
from app.utils.logger import setup_logging

console = Console(force_terminal=True)

logger = setup_logging()


class AgentBotService:
    def __init__(self, llm: BaseChatModel, checkpointer: BotMemory):
        self.llm: BaseChatModel = llm
        self.checkpointer = checkpointer

        self.aws_config: S3ConfigService = S3ConfigService()
        self.aws_s3_bucket_name: str = env_config.aws_bucket_name
        self.aws_s3_file_name: str = env_config.aws_file_name

        self.redis_service = RedisService()
        self.bot_cached_key = RedisCacheKeys.AGENT_BOT_PROMPT.value
        self._prompt_cache = None

        self._agent_graph = None

    def _get_llm_prompt(self) -> str:
        """
        Checks Redis cache for the prompt, if not found,
        fetches the prompt from S3 and caches it.

        Returns:
            str: The prompt.
        """
        if self._prompt_cache:
            return self._prompt_cache

        cached_prompt = self.redis_service.get_cached_prompt(self.bot_cached_key)
        if cached_prompt:
            logger.info("Prompt loaded from Redis.")
            self._prompt_cache = cached_prompt
            return cached_prompt

        try:
            logger.info(f"Fetching fresh prompt from S3: {self.aws_s3_file_name}")
            content = self.aws_config.get_file_content(
                self.aws_s3_bucket_name, self.aws_s3_file_name
            )
            self.redis_service.set_cached_prompt(
                self.bot_cached_key, content, expiry=60 * 60 * 24
            )  # Cache for 24 hours

            self._prompt_cache = content
            return content

        except Exception as e:
            logger.exception(f"Failed to load prompt from S3 {e}")
            raise

    def _get_agent_graph(self):
        """
        Get or create the LangGraph agent graph.

        Returns:
            Compiled graph: The LangGraph graph
        """
        if self._agent_graph is None:
            prompt = self._get_llm_prompt()
            self._agent_graph = ChatWorkflow(
                llm=self.llm,
                tools=RAG_BOT_TOOLS,
                system_prompt=prompt,
                checkpointer=self.checkpointer,
            )
        return self._agent_graph

    async def _generate_title(self, query: str) -> str:
        """
        Generate a concise title for the conversation using the LLM.

        Args:
            query (str): The initial query to base the title on.

        Returns:
            str: A generated title (6-8 words max).
        """

        prompt = f"""Generate a concise title (max 6 words) for this query:
"{query}"

Title:"""

        try:
            response = await self.llm.ainvoke(prompt)
            title = response.content.strip().strip('"').strip("'")
            title = title.split("\n")[0].strip()
            return title if title else query[:30]
        except Exception:
            return query[:30]

    async def invoke_agent(
        self, query: str, order_id: str | None, user_id: str, session_id: str
    ):
        context_query = f"Regarding Order Id {order_id}: {query}" if order_id else query
        title = await self._generate_title(context_query)

        config = {
            "configurable": {"thread_id": session_id},
            "metadata": {"user_id": user_id, "title": title},
        }

        try:
            graph_wrapper = self._get_agent_graph()
            logger.info(f"Invoking agent with query: {context_query[:50]}...")

            # Use the internal compiled graph directly
            graph = graph_wrapper.graph

            initial_state: AgentState = {
                "messages": [HumanMessage(content=context_query)],
                "sender": "user",
                "order_id": order_id,
                "query": context_query,
                "variables": None,
                "metadata": {"user_id": user_id, "title": title},
            }

            async for event in graph.astream_events(
                initial_state, config=config, version="v2"
            ):
                kind = event["event"]

                match kind:
                    # 1. Handle Tool Start
                    case "on_tool_start":
                        tool_name = event.get("name")
                        yield f"data: {json.dumps({'status': f'Searching {tool_name}...'})}\n\n"

                    # 2. Handle Token Streaming (Model tokens)
                    case "on_chat_model_stream":
                        content = event["data"].get("chunk", {})
                        text = getattr(content, "content", "")
                        if text:
                            yield f"data: {json.dumps({'token': text})}\n\n"

                    # 3. Handle Chain Streaming (Final Node outputs)
                    case "on_chain_stream":
                        data = event.get("data", {})
                        if "chunk" in data:
                            chunk = data["chunk"]
                            if isinstance(chunk, dict) and "messages" in chunk:
                                last_msg = chunk["messages"][-1]
                                if last_msg.type == "ai" and last_msg.content:
                                    yield f"data: {json.dumps({'token': last_msg.content})}\n\n"

                    case "on_chat_model_end":
                        output = event["data"].get("output", {})
                        console.print(
                            Panel(
                                Pretty(output),
                                title="Thinking...",
                                border_style="green",
                            )
                        )

        except Exception as e:
            logger.error(f"Streaming Error: {str(e)}", exc_info=True)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

        finally:
            yield "data: [DONE]\n\n"

    async def get_chat_history(self, session_id: str) -> ChatHistoryResponse:
        """
        Fetch chat history from a given session ID.

        Args:
            session_id (str): The session ID to fetch history for.

        Returns:
            list: A list of messages in the conversation.
        """

        config = {"configurable": {"thread_id": session_id}}
        try:
            state = await self.checkpointer.aget(config)
            messages = (
                state.get("channel_values", {}).get("messages", []) if state else []
            )
            return [
                self._format_message(msg)
                for msg in messages
                if self._is_displayable(msg)
                and (msg.content if hasattr(msg, "content") else msg.get("content"))
                != ""
            ]

        except Exception as e:
            logger.error(f"Error fetching chat history: {e}")
            return []

    def _is_displayable(self, msg) -> bool:
        content = msg.content if hasattr(msg, "content") else msg.get("content", "")
        m_type = msg.type if hasattr(msg, "type") else msg.get("type", "")

        is_empty = content.strip() == ""
        is_technical = m_type in ["tool", "system"]
        is_summary = "summary of the conversation" in content.lower()

        return not (is_empty or is_technical or is_summary)

    def _format_message(self, msg):
        """Converts a message object/dict into a clean API-friendly dictionary."""
        m = (
            msg.dict()
            if hasattr(msg, "dict")
            else (msg if isinstance(msg, dict) else {})
        )

        metadata = m.get("response_metadata", {})

        return {
            "content": m.get("content", ""),
            "type": m.get("type", "unknown"),
            "created_at": metadata.get("created_at", "unknown"),
        }
