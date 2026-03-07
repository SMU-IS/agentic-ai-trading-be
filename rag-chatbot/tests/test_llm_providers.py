from unittest.mock import patch

import pytest

from app.core.constant import LLMProviders
from app.providers.llm.registry import get_strategy
from app.providers.llm.strategy import GeminiStrategy, GroqStrategy, OllamaStrategy


def test_get_strategy_success():
    strategy = get_strategy(LLMProviders.GEMINI)
    assert isinstance(strategy, GeminiStrategy)


def test_get_strategy_failure():
    with pytest.raises(ValueError):
        get_strategy("invalid_provider")


@patch("app.providers.llm.strategy.ChatOllama")
def test_ollama_strategy(mock_ollama):
    strategy = OllamaStrategy()
    strategy.create_model()
    mock_ollama.assert_called_once()


@patch("app.providers.llm.strategy.ChatGoogleGenerativeAI")
def test_gemini_strategy(mock_gemini):
    strategy = GeminiStrategy()
    strategy.create_model()
    mock_gemini.assert_called_once()


@patch("app.providers.llm.strategy.ChatGroq")
def test_groq_strategy(mock_groq):
    strategy = GroqStrategy()
    strategy.create_model()
    mock_groq.assert_called_once()
