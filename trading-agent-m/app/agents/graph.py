from app.core.config import env_config
from app.services.trading_workflow import TradingWorkflow
from langchain_ollama import ChatOllama

# 1. Initialize clients via config/env
llm = ChatOllama(
    model=env_config.large_language_model,
    temperature=env_config.ollama_temperature,
    base_url=env_config.ollama_base_url,
)
broker = None
trading_agent = TradingWorkflow(llm_client=llm, broker_client=broker)
app_workflow = trading_agent
