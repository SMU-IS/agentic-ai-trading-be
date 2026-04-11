from abc import ABC, abstractmethod
from typing import override

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langchain_ollama import ChatOllama
from pydantic import SecretStr

from app.core.config import env_config


class LLMStrategy(ABC):
    @abstractmethod
    def create_model(self) -> BaseChatModel:
        pass


class OllamaStrategy(LLMStrategy):
    @override
    def create_model(self) -> BaseChatModel:
        return ChatOllama(
            model=env_config.large_language_model,
            base_url=env_config.ollama_base_url,
            temperature=env_config.temperature,
            num_predict=env_config.max_completion_tokens,
        )


class GeminiStrategy(LLMStrategy):
    @override
    def create_model(self) -> BaseChatModel:
        return ChatGoogleGenerativeAI(
            model=env_config.large_language_model,
            google_api_key=env_config.llm_api_key,
            temperature=env_config.temperature,
            max_output_tokens=env_config.max_completion_tokens,
            streaming=True,
            convert_system_message_to_human=True,
        )


class GroqStrategy(LLMStrategy):
    @override
    def create_model(self) -> BaseChatModel:
        return ChatGroq(
            model=env_config.large_language_model,
            api_key=SecretStr(env_config.llm_api_key),
            temperature=0,
            max_tokens=env_config.max_completion_tokens,
            streaming=True,
            max_retries=2,
        )


class NvidiaStrategy(LLMStrategy):
    @override
    def create_model(self) -> BaseChatModel:
        return ChatNVIDIA(
            model=env_config.large_language_model,
            api_key=env_config.llm_api_key,
            temperature=env_config.temperature,
            top_p=0.95,
            max_tokens=16384,
            reasoning_budget=16384,
            chat_template_kwargs={"enable_thinking": False},
        )
