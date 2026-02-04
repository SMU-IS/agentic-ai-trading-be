from .database_tools import (
    get_general_news_context_and_result,
    get_trade_history_details,
)

RAG_BOT_TOOLS = [get_trade_history_details, get_general_news_context_and_result]
