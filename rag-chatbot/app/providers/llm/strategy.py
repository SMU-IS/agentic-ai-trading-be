from abc import ABC, abstractmethod

from app.core.config import env_config
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_ollama import ChatOllama


class LLMStrategy(ABC):
    @abstractmethod
    def create_model(self) -> BaseChatModel:
        pass


# Ollama
class OllamaStrategy(LLMStrategy):
    def create_model(self) -> BaseChatModel:
        return ChatOllama(
            model=env_config.large_language_model,
            base_url=env_config.ollama_base_url,
            temperature=0,
            num_predict=env_config.max_completion_tokens,
        )


# class GeminiStrategy(LLMStrategy):
