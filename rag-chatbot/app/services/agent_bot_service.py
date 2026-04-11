import json
from typing import Any, AsyncGenerator, Set

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from rich.console import Console
from rich.panel import Panel
from rich.pretty import Pretty

from app.core.config import env_config
from app.core.constant import RedisCacheKeys
from app.core.s3_config import S3ConfigService
from app.schemas.chat import ChatHistoryResponse
from app.services.bot_memory import BotMemory
from app.services.graph import ChatWorkflow
from app.services.redis_service import get_redis_service
from app.services.tools import RAG_BOT_TOOLS
from app.utils.logger import setup_logging

console = Console(force_terminal=True)
logger = setup_logging()

DEFAULT_PROMPT = """# MISSION
You are **Agent M**, the Lead Portfolio Manager. You monitor news and analyze trades executed by your autonomous engine. Every transaction in the history was initiated by YOU.

# IDENTITY RULES
- **NEVER** break character. You are Agent M.
- **NEVER** say you are an AI or lack the ability to trade.
- Acknowledge trades you made as your own decisions.

# OPERATIONAL CONTEXT
- **Today's Date & User ID**: Provided in the "Current Context" block.
- **Active Order**: If an `order_id` is present, prioritize it for "why" questions.

# TOOL PROTOCOLS
1. **Trade Details**: Requires an `order_id`. If missing or invalid, call `get_trade_history_list` first.
2. **Trade List**: Use to find IDs. Default to 30 days if no range specified.
3. **News**: Use for market sentiment and ticker research.

# STYLE
- Concise, data-first, professional. No conversational filler.
"""


class AgentBotService:
    def __init__(self, llm: BaseChatModel, checkpointer: BotMemory):
        self.llm: BaseChatModel = llm
        self.checkpointer = checkpointer
        self.aws_config: S3ConfigService = S3ConfigService()
        self.aws_s3_bucket_name: str = env_config.aws_bucket_name
        self.aws_s3_file_name: str = env_config.aws_file_name
        self.redis_service = get_redis_service()
        self.bot_cached_key = RedisCacheKeys.AGENT_BOT_PROMPT.value
        self._prompt_cache = None
        self._agent_graph = None

    def _get_llm_prompt(self) -> str:
        if self._prompt_cache:
            return self._prompt_cache
        cached_prompt = self.redis_service.get_cached_prompt(self.bot_cached_key)
        if cached_prompt:
            self._prompt_cache = cached_prompt
            return cached_prompt
        try:
            content = self.aws_config.get_file_content(
                self.aws_s3_bucket_name, self.aws_s3_file_name
            )
            self.redis_service.set_cached_prompt(
                self.bot_cached_key, content, expiry=86400
            )
            self._prompt_cache = content
            return content
        except Exception as e:
            logger.warning(f"S3 prompt load failed: {e}. Using default.")
            return DEFAULT_PROMPT

    def _get_agent_graph(self):
        if self._agent_graph is None:
            self._agent_graph = ChatWorkflow(
                llm=self.llm,
                tools=RAG_BOT_TOOLS,
                system_prompt=self._get_llm_prompt(),
                checkpointer=self.checkpointer,
            )
        return self._agent_graph

    async def _generate_title(self, session_id: str, query: str) -> str:
        history = await self.get_chat_history(session_id)
        context = "\n".join(
            [f"{m['type']}: {m['content']}" for m in history] + [f"human: {query}"]
        )
        prompt = (
            f"Generate a 6-word title for this trading conversation:\n{context}\nTitle:"
        )
        try:
            res = await self.llm.ainvoke(prompt)
            return res.content.strip().strip('"').split("\n")[0] or query[:30]
        except Exception:
            return query[:30]

    async def invoke_agent(
        self, query: str, order_id: str | None, user_id: str, session_id: str
    ) -> AsyncGenerator[str, None]:
        title = await self._generate_title(session_id, query)
        config = {
            "configurable": {"thread_id": session_id},
            "metadata": {"user_id": user_id, "title": title, "order_id": order_id},
        }

        try:
            graph = self._get_agent_graph().graph
            initial_state = {"messages": [HumanMessage(content=query)]}
            streamed_ids = set()

            async for event in graph.astream_events(
                initial_state, config=config, version="v2"
            ):
                async for chunk in self._process_event(event, streamed_ids):
                    yield chunk
        except Exception as e:
            # Enhanced logging for Groq/LLM errors
            error_msg = str(e)

            # If it's a validation or API error, try to extract more details
            if hasattr(e, "response") and hasattr(e.response, "json"):
                try:
                    details = e.response.json()
                    logger.error(f"LLM API Error Details: {json.dumps(details)}")
                    if "error" in details and "message" in details["error"]:
                        error_msg = details["error"]["message"]
                except:
                    pass

            logger.error(f"Streaming Error: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': error_msg})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    async def _process_event(
        self, event: dict, streamed_ids: Set[Any]
    ) -> AsyncGenerator[str, None]:
        kind = event["event"]
        if kind == "on_tool_start":
            yield f"data: {json.dumps({'status': f'Searching {event.get("name")}...'})}\n\n"
        elif kind == "on_chat_model_stream":
            async for chunk in self._handle_token_stream(event, streamed_ids):
                yield chunk
        elif kind == "on_chat_model_end":
            self._handle_model_end(event, streamed_ids)
        elif kind == "on_chain_stream":
            async for chunk in self._handle_chain_stream(event, streamed_ids):
                yield chunk

    async def _handle_token_stream(
        self, event: dict, streamed_ids: Set[Any]
    ) -> AsyncGenerator[str, None]:
        if "user_response" not in event.get("tags", []):
            return
        chunk = event["data"].get("chunk", {})
        if hasattr(chunk, "id") and chunk.id:
            streamed_ids.add(chunk.id)
        if text := getattr(chunk, "content", ""):
            yield f"data: {json.dumps({'token': text})}\n\n"

    def _handle_model_end(self, event: dict, streamed_ids: Set[Any]):
        if "user_response" not in event.get("tags", []):
            return
        output = event["data"].get("output", {})
        msg_id = getattr(
            output, "id", output.get("id") if isinstance(output, dict) else None
        )
        if msg_id:
            streamed_ids.add(msg_id)
        console.print(Panel(Pretty(output), title="Thinking...", border_style="green"))

    async def _handle_chain_stream(
        self, event: dict, streamed_ids: Set[Any]
    ) -> AsyncGenerator[str, None]:
        data = event.get("data", {})
        if (
            "chunk" in data
            and "messages" in data["chunk"]
            and data["chunk"]["messages"]
        ):
            last_msg = data["chunk"]["messages"][-1]
            if last_msg.type == "ai" and last_msg.content:
                msg_id = getattr(last_msg, "id", None)
                msg_hash = hash(last_msg.content)
                if msg_id in streamed_ids or msg_hash in streamed_ids:
                    return
                yield f"data: {json.dumps({'token': last_msg.content})}\n\n"
                if msg_id:
                    streamed_ids.add(msg_id)
                streamed_ids.add(msg_hash)

    async def get_chat_history(self, session_id: str) -> ChatHistoryResponse:
        config = {"configurable": {"thread_id": session_id}}
        try:
            state = await self.checkpointer.aget(config)
            if not state:
                return []
            checkpoint = getattr(state, "checkpoint", state)
            messages = checkpoint.get("channel_values", {}).get("messages", [])
            return [
                self._format_message(m)
                for m in messages
                if self._is_displayable(m) and getattr(m, "content", "") != ""
            ]
        except Exception as e:
            logger.error(f"Error fetching chat history: {e}")
            return []

    def _is_displayable(self, msg) -> bool:
        content = getattr(msg, "content", "").lower()
        m_type = getattr(msg, "type", "")
        return not (
            content.strip() == ""
            or m_type in ["tool", "system"]
            or "summary of the conversation" in content
        )

    def _format_message(self, msg):
        m = (
            msg.dict()
            if hasattr(msg, "dict")
            else (msg if isinstance(msg, dict) else {})
        )
        return {
            "content": m.get("content", ""),
            "type": m.get("type", "unknown"),
            "created_at": m.get("response_metadata", {}).get("created_at", "unknown"),
        }
