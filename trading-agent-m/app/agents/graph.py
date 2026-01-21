from app.services.trading_workflow import TradingWorkflow
from langchain_openai import ChatOpenAI

# from app.core.broker import BrokerClient # Assuming you have a broker wrapper

# 1. Initialize your Clients via config/env
llm = ChatOpenAI(model="gpt-4o", temperature=0)
broker = None


trading_agent = TradingWorkflow(llm_client=llm, broker_client=broker)
app_workflow = trading_agent
