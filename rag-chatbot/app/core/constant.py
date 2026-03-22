from enum import Enum


class APIPath(str, Enum):
    HEALTH_CHECK = "/healthcheck"
    CHAT = "/chat"
    CHAT_HISTORY = "/chat/history/{session_id}"
    THREADS = "/threads"


class LangChainEvent(str, Enum):
    """Event names for both LangChain and LangGraph (compatible)."""

    CHAT_MODEL_STREAM = "on_chat_model_stream"
    CHAT_MODEL_END_STREAM = "on_chat_model_end"
    TOOL_START = "on_tool_start"
    TOOL_END = "on_tool_end"
    CHAIN_START = "on_chain_start"
    CHAIN_END = "on_chain_end"
    AGENT_END = "on_agent_end"
    AGENT_STREAM = "on_agent_stream"


class LLMProviders(str, Enum):
    OLLAMA = "ollama"
    GEMINI = "gemini"
    GROQ = "groq"
    NVIDIA = "nvidia"


class RedisCacheKeys(str, Enum):
    AGENT_BOT_PROMPT = "agent_bot_prompt"
