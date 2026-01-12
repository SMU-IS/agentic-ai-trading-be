from broker_client import AlpacaBrokerClient, BrokerConfig
import os
from dotenv import load_dotenv
load_dotenv()

cfg = BrokerConfig(
    api_key=os.environ["ALPACA_API_KEY"],
    api_secret=os.environ["ALPACA_API_SECRET"],
    paper=True,
)
broker = AlpacaBrokerClient(cfg)

# print(broker.get_account())
# order = broker.submit_market_order(symbol="AAPL", side="buy", qty=1)
# print(order)

account_info = broker.get_account()
print(account_info)