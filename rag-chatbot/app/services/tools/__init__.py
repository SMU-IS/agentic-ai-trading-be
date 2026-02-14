from .general_news import get_general_news
from .trade_history import get_trade_history_details

RAG_BOT_TOOLS = [get_general_news, get_trade_history_details]
