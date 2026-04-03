import time
from operator import itemgetter
from typing import Any, AsyncGenerator, Dict

from langchain_core.chat_history import (
    BaseChatMessageHistory,
    InMemoryChatMessageHistory,
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

# In-memory store for session histories with access timestamps
# Format: { session_id: {"history": InMemoryChatMessageHistory, "last_accessed": timestamp} }
store: Dict[str, Dict[str, Any]] = {}


class InfoAgentService:
    def __init__(self):
        self.llm = self._get_llm()
        self.embeddings = self._get_embeddings()
        self.vector_store = self._get_vector_store()
        self.retriever = self.vector_store.as_retriever(search_kwargs={"k": 3})
        self.chain = self._build_chain()

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
                    "You are an Information Agent (Agent m) for the Agentic AI Trading application. "
                    "Your goal is to answer user questions about how the application works, its features, and technical details. "
                    "Use the following pieces of retrieved context to answer the question. "
                    "If you don't know the answer, just say that you don't know, don't try to make up an answer.\n\n"
                    "Context:\n{context}",
                ),
                MessagesPlaceholder(variable_name="history"),
                ("human", "{question}"),
            ]
        )

        def format_docs(docs):
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
        current_time = time.time()

        # Cleanup logic: Remove sessions older than 1 hour (3600 seconds)
        expired_sessions = [
            sid
            for sid, data in store.items()
            if current_time - data["last_accessed"] > 3600
        ]
        if expired_sessions:
            logger.info(f"Cleaning up {len(expired_sessions)} expired chat sessions.")
            for sid in expired_sessions:
                del store[sid]

        if session_id not in store:
            store[session_id] = {
                "history": InMemoryChatMessageHistory(),
                "last_accessed": current_time,
            }
        else:
            store[session_id]["last_accessed"] = current_time

        return store[session_id]["history"]

    async def ainvoke(
        self, question: str, session_id: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        config = {"configurable": {"session_id": session_id}}

        chain_with_history = RunnableWithMessageHistory(
            self.chain,
            self.get_session_history,
            input_messages_key="question",
            history_messages_key="history",
        )

        logger.info(f"Invoking info agent with question: {question[:50]}...")

        async for event in chain_with_history.astream_events(
            {"question": question},
            config=config,
            version="v2",
        ):
            kind = event["event"]

            if kind == "on_retriever_start":
                yield {"status": "Searching knowledge base..."}

            elif kind == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if chunk and hasattr(chunk, "content"):
                    if chunk.content:
                        yield {"token": chunk.content}

            elif kind == "on_chat_model_end":
                output = event["data"].get("output")
                if output:
                    console.print(
                        Panel(
                            Pretty(output),
                            title="Thinking...",
                            border_style="green",
                        )
                    )
