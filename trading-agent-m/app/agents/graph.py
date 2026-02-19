## OLLAMA ##
# from app.core.config import env_config
# from app.services.trading_workflow import TradingWorkflow
# from langchain_ollama import ChatOllama

# # 1. Initialize clients via config/env
# llm = ChatOllama(
#     model=env_config.large_language_model,
#     temperature=env_config.ollama_temperature,
#     base_url=env_config.ollama_base_url,
# )

# trading_agent = TradingWorkflow(llm_client=llm)
# app_workflow = trading_agent


from app.core.config import env_config
from app.services.trading_workflow import TradingWorkflow
from langchain_perplexity import ChatPerplexity  # Requires: pip install langchain-perplexity


# 1. Initialize clients via config/env
llm = ChatPerplexity(
    pplx_api_key=env_config.perplexity_api_key,  # PPLX_API_KEY env var [web:11]
    model=env_config.perplexity_model,  # Search-enabled model for trading/news [web:19][web:21]
    temperature=env_config.perplexity_temperature or 0.2,
)

trading_agent = TradingWorkflow(llm_client=llm)
app_workflow = trading_agent