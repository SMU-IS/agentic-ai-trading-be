from app.core.constant import LLMProviders
from app.providers.llm.strategy import OllamaStrategy

LLM_STRATEGIES = {
    LLMProviders.OLLAMA: OllamaStrategy(),
    # "LLMProviders.GEMINI": GeminiStrategy(),
}


def get_strategy(provider_name: LLMProviders):
    """
    Retrieves the strategy based on config name.
    """

    strategy = LLM_STRATEGIES.get(provider_name)
    if not strategy:
        raise ValueError(f"Provider '{provider_name}' not found in registry.")

    return strategy
