"""
LLM factory for multi-model support.

Maps a model name (stored in agent_setting.llm_model) to a LangChain chat model
instance that supports with_structured_output.

Supported models:
  perplexity  — ChatPerplexity  (online search, news-aware)
  claude      — ChatAnthropic   (strong reasoning)
  openai      — ChatOpenAI      (reliable structured output)
"""

from functools import lru_cache
from app.core.config import env_config


def get_llm(model: str = "perplexity"):
    """
    Return a LangChain chat model for the given model name.
    Falls back to Perplexity for unknown values.
    """
    model = (model or "perplexity").lower()

    if model == "claude":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            api_key=env_config.anthropic_api_key,
            model=env_config.anthropic_model,
            temperature=0.2,
        )

    if model == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            api_key=env_config.openai_api_key,
            model=env_config.openai_model,
            temperature=0.2,
        )

    # default: perplexity
    from langchain_perplexity import ChatPerplexity
    return ChatPerplexity(
        pplx_api_key=env_config.perplexity_api_key,
        model=env_config.perplexity_model or "sonar",
        temperature=float(env_config.perplexity_temperature or 0.2),
    )
