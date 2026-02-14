from abc import ABC, abstractmethod

from app.core.config import env_config
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
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
            temperature=env_config.temperature,
            num_predict=env_config.max_completion_tokens,
        )


class GeminiStrategy(LLMStrategy):
    def create_model(self) -> BaseChatModel:
        return ChatGoogleGenerativeAI(
            model=env_config.large_language_model,
            google_api_key=env_config.gemini_api_key,
            temperature=env_config.temperature,
            max_output_tokens=env_config.max_completion_tokens,
            streaming=True,
            convert_system_message_to_human=True,
        )
