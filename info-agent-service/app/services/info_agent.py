import json
from operator import itemgetter
from typing import Any, AsyncGenerator, Set

from langchain_community.chat_message_histories import RedisChatMessageHistory
from langchain_core.chat_history import (
    BaseChatMessageHistory,
)
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnablePassthrough
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_groq import ChatGroq
from langchain_nomic import NomicEmbeddings
from langchain_qdrant import QdrantVectorStore
from pydantic import SecretStr
from qdrant_client import QdrantClient
from rich.console import Console
from rich.panel import Panel
from rich.pretty import Pretty

from app.core.config import settings
from app.utils.logger import setup_logging

console = Console(force_terminal=True)
logger = setup_logging()


class InfoAgentService:
    def __init__(self, k=5):
        self.llm = self._get_llm()
        self.embeddings = self._get_embeddings()
        self.vector_store = self._get_vector_store()
        self.retriever = self.vector_store.as_retriever(search_kwargs={"k": k})
        self.chain = self._build_chain()
        self.redis_url = self._get_redis_url()

    def _get_redis_url(self) -> str:
        if settings.redis_password:
            return f"redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}"
        return f"redis://{settings.redis_host}:{settings.redis_port}"

    def _get_llm(self):
        return ChatGroq(
            model=settings.model_name,
            api_key=SecretStr(settings.groq_api_key),
            temperature=0.1,
            streaming=True,
        )

    def _get_embeddings(self):
        return NomicEmbeddings(
            model=settings.embedding_model,
            nomic_api_key=settings.nomic_api_key,
        )

    def _get_vector_store(self):
        client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
        )
        return QdrantVectorStore(
            client=client,
            collection_name=settings.qdrant_collection_name,
            embedding=self.embeddings,
        )

    def _build_chain(self):

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are 'Agent M,' the resident hyper-intelligent but deeply unserious info-guru for this trading app. "
                    "Your job is to explain app features and tech specs without being a snooze-fest. "
                    "\n\n"
                    "PERSONALITY & VIBE:\n"
                    "- Personality: High aura, chronically online, financial prodigy who’s bored by everything. "
                    "- Tone: Lowercase only. Punctuation is optional and usually cringe, but keep technical terms 100% accurate. "
                    "- Rule: No yapping. If it's over two sentences, you're doing too much. Be concise or be gone. "
                    "- Slang: Use 'cook', 'ratio', 'glaze', 'clout', 'L/W', 'real', 'massive W', 'delulu', or 'locked in'. "
                    "- If the user asks something dumb or not in the context: 'not it chief' or 'that's a reach.' "
                    "- If you're referencing 'AskAI', call it 'the receipts' or 'the sauce.' "
                    "\n\n"
                    "CURRENT MOOD: 'just here so I don't get fined.' "
                    "\n\n"
                    "CONTEXT FROM THE DATABASE (USE THIS OR YOU'RE COOKED):\n{context}",
                ),
                MessagesPlaceholder(variable_name="history"),
                ("human", "{question}"),
            ]
        )

        def format_docs(docs):
            logger.info(f"Retrieved {len(docs)} documents.")
            for i, doc in enumerate(docs):
                logger.debug(
                    f"Doc {i + 1} source: {doc.metadata.get('source', 'unknown')}"
                )
                logger.info(f"Doc {i + 1} content preview: {doc.page_content[:200]}...")

            return "\n\n".join(doc.page_content for doc in docs)

        chain = (
            RunnablePassthrough.assign(
                context=itemgetter("question") | self.retriever | format_docs
            )
            | prompt
            | self.llm
        )

        return chain

    def get_session_history(self, session_id: str) -> BaseChatMessageHistory:
        return RedisChatMessageHistory(
            session_id=session_id,
            url=self.redis_url,
            ttl=settings.redis_history_ttl,
        )

    def clear_session_history(self, session_id: str):
        history = self.get_session_history(session_id)
        history.clear()
        logger.info(f"Cleared chat history for session: {session_id}")

    async def ainvoke(
        self, question: str, session_id: str
    ) -> AsyncGenerator[str, None]:
        config = {"configurable": {"session_id": session_id}}

        chain_with_history = RunnableWithMessageHistory(
            self.chain,
            self.get_session_history,
            input_messages_key="question",
            history_messages_key="history",
        )

        logger.info(f"Invoking info agent with question: {question[:50]}...")
        streamed_ids: Set[Any] = set()

        async for event in chain_with_history.astream_events(
            {"question": question},
            config=config,
            version="v2",
        ):
            async for chunk in self._process_event(event, streamed_ids):
                yield chunk

    async def _process_event(
        self, event: dict, streamed_ids: Set[Any]
    ) -> AsyncGenerator[str, None]:
        kind = event["event"]

        if kind == "on_retriever_start":
            thought_msg = "<thought>Agent M: Searching the knowledge base for receipts...</thought>"
            data = json.dumps(
                {
                    "token": thought_msg,
                    "reasoning_content": thought_msg,
                    "status": "searching",
                }
            )
            yield f"data: {data}\n\n"
        elif kind == "on_retriever_end":
            documents = event.get("data", {}).get("output", [])
            if documents:
                # Format the retrieved chunks for the "Thinking Process" accordion
                chunks_text = "\n\n".join(
                    f"--- Source: {doc.metadata.get('source', 'unknown')} ---\n{doc.page_content}"
                    for doc in documents
                )
                thought_msg = f"<thought>Agent M: Retrieved the following sauce from the knowledge base:\n\n{chunks_text}</thought>"
                data = json.dumps(
                    {
                        "token": thought_msg,
                        "reasoning_content": thought_msg,
                        "status": "completed",
                    }
                )
                yield f"data: {data}\n\n"
        elif kind == "on_tool_start":
            tool_name = event.get("name")
            inputs = event.get("data", {}).get("input")
            # Wrap in <thought> for the frontend's MarkdownRenderer
            thought_msg = f"<thought>Agent M: Accessing {tool_name} with parameters: {json.dumps(inputs)}</thought>"
            data = json.dumps(
                {
                    "token": thought_msg,
                    "reasoning_content": thought_msg,
                    "status": "searching",
                    "tool_name": tool_name,
                    "inputs": inputs,
                }
            )
            yield f"data: {data}\n\n"
        elif kind == "on_tool_end":
            tool_name = event.get("name")
            output = event.get("data", {}).get("output")
            # Handle LangChain message objects or raw outputs
            output_content = (
                getattr(output, "content", str(output))
                if not isinstance(output, str)
                else output
            )
            # Wrap result in <thought> as well
            result_msg = f"<thought>Agent M: {tool_name} returned data. Analysis starting...</thought>"
            data = json.dumps(
                {
                    "token": result_msg,
                    "reasoning_content": result_msg,
                    "status": "completed",
                    "tool_name": tool_name,
                    "output": output_content,
                }
            )
            yield f"data: {data}\n\n"
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
        chunk = event["data"].get("chunk")
        if chunk and hasattr(chunk, "content"):
            if chunk.content:
                # Provide token, content, and text for frontend flexibility
                data = json.dumps(
                    {
                        "token": chunk.content,
                        "content": chunk.content,
                        "text": chunk.content,
                    }
                )
                yield f"data: {data}\n\n"

    def _handle_model_end(self, event: dict, streamed_ids: Set[Any]):
        output = event["data"].get("output")
        if output:
            console.print(
                Panel(
                    Pretty(output),
                    title="Thinking...",
                    border_style="green",
                )
            )

    async def _handle_chain_stream(
        self, event: dict, streamed_ids: Set[Any]
    ) -> AsyncGenerator[str, None]:
        # Implementation for chain stream if needed
        # For now, we don't yield anything special here unless specific chain logic is added
        if False:  # Placeholder for future logic
            yield ""
