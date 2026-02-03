from enum import Enum


class APIPath(str, Enum):
    HEALTH_CHECK = "/healthcheck"
    ORDER = "/order"


class LangChainEvent(str, Enum):
    CHAT_MODEL_STREAM = "on_chat_model_stream"
    TOOL_START = "on_tool_start"
    TOOL_END = "on_tool_end"
    CHAIN_START = "on_chain_start"
    CHAIN_END = "on_chain_end"


class LLMProviders(str, Enum):
    OLLAMA = "ollama"
