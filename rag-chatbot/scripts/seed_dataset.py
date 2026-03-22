"""
Seed script for populating the LangSmith 'agent-bot-langgraph-dataset' dataset with
labelled examples for tool call evaluation.

Each example contains:
- input: A user query (and optional order_id) passed to the agent
- output: Ground truth labels for what the agent should do:
    - tool_called (bool): Whether a tool should be invoked
    - tool_name (str | None): Which tool should be called, or None if no tool

Tools under test:
- get_trade_history_details: Called when user asks WHY a trade was made,
  what indicators triggered it, or requests technical reasoning for a
  specific order_id.
- get_general_news: Called when user asks about market news, stock sentiment,
  sector trends, or any real-time financial information without an order_id.
- None: No tool should be called for greetings, general financial education
  questions, chitchat, or queries missing a required order_id.

Usage:
    python3 -m scripts.seed_dataset


- 50 cases for get_trade_history_details (when order_id is present).
- 50 cases for get_general_news (market news and trends).
- 50 cases for general chitchat and financial education (no tool call).
- 50 cases for missing order_id (routing to clarify, no tool call).
"""

import logging
import os

from langsmith import Client

from app.core.config import env_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("seed-dataset")

os.environ["LANGSMITH_API_KEY"] = env_config.langsmith_api_key
client = Client()

test_cases = [
    # ─────────────────────────────────────────────
    # get_trade_history_details — clear cases (50)
    # ─────────────────────────────────────────────
    {
        "input": {"query": "Why did we sell AAPL on order #555?", "order_id": "555"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "What were the RSI values when order #777 was made?",
            "order_id": "777",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "What was the reasoning behind order #4400?",
            "order_id": "4400",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "Why did the system buy TSLA on order #3300?",
            "order_id": "3300",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "What technical indicators triggered order #8811?",
            "order_id": "8811",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "Show me the ATR at time of order #2200",
            "order_id": "2200",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "What was the trade logic for order #9900?",
            "order_id": "9900",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "Explain why order #6655 was placed", "order_id": "6655"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "What signal caused order #1122?", "order_id": "1122"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "Break down the reasoning for order #5544",
            "order_id": "5544",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "Was order #3311 based on RSI?", "order_id": "3311"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "What momentum indicator triggered order #7788?",
            "order_id": "7788",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "Why did we exit the position on order #4422?",
            "order_id": "4422",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "What was the entry rationale for order #9977?",
            "order_id": "9977",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "Explain the trade decision for order #6633",
            "order_id": "6633",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "Why was NVDA bought in order #2211?", "order_id": "2211"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "What indicators were present for order #8866?",
            "order_id": "8866",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "Justify the sell on order #5533", "order_id": "5533"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "Was there a stop loss trigger on order #1199?",
            "order_id": "1199",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "What was the market condition when order #3377 was placed?",
            "order_id": "3377",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "What was the P&L on order #4455?", "order_id": "4455"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "Show me the trade details for order #6611",
            "order_id": "6611",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "What price did we enter on order #9933?",
            "order_id": "9933",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "Was order #2277 a profitable trade?", "order_id": "2277"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "What was the exit strategy for order #7744?",
            "order_id": "7744",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "Bollinger bands for order #123?", "order_id": "123"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "MACD signal on order #456", "order_id": "456"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "Why did we buy AAPL here?", "order_id": "ord_882"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "indicators for order 991", "order_id": "991"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "Technical reasoning for trade 552", "order_id": "552"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "Why did we sell TSLA in order 332?", "order_id": "332"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "Show reasoning for #1212", "order_id": "1212"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "What was the conviction level of #2323?",
            "order_id": "2323",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "ATR value for #3434", "order_id": "3434"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "Momentum reading for #4545", "order_id": "4545"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "Why buy NVDA on #5656?", "order_id": "5656"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "Rationale behind sell #6767", "order_id": "6767"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "Indicators present for #7878", "order_id": "7878"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "Check logic for #8989", "order_id": "8989"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "Did order #1313 have a high RSI?", "order_id": "1313"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "What chart pattern led to #2424?", "order_id": "2424"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "Explain buy signal for #3535", "order_id": "3535"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "Why exit #4646?", "order_id": "4646"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "Indicators for sell #5757", "order_id": "5757"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "Logic on buy #6868", "order_id": "6868"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "What triggered trade #7979?", "order_id": "7979"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "Show me the technicals for #8181", "order_id": "8181"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "Why buy AAPL in order 9191?", "order_id": "9191"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "What were indicators for #1010?", "order_id": "1010"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "Explain logic behind #2020", "order_id": "2020"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    # ─────────────────────────────────────────────
    # get_general_news — clear cases (50)
    # ─────────────────────────────────────────────
    {
        "input": {"query": "What's the latest news on NVDA?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "Why is the market down today?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "What's happening with AAPL stock?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "Any news on Tesla earnings?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "What's the market sentiment today?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "Is there any news driving MSFT up?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "What are analysts saying about AMZN?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "Any Fed news today?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "Why did tech stocks drop?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "What's the latest on interest rates?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "Is there a market rally happening?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "What sectors are hot right now?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "Any earnings beats today?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "What's causing the VIX spike?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "News on semiconductor stocks"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "What is PLTR doing today?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "Any news on the S&P 500?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "What are the hot stocks this week?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "Market outlook for today"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "Any macro events moving the market?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "NVDA earnings report news"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "AAPL stock sentiment updates"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "TSLA analyst upgrades news"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "MSFT quarterly results news"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "AMD vs INTEL competition news"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "What is driving the energy sector today?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "Is inflation affecting stock prices?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "Any news on the banking sector?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "What's the outlook for gold prices?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "Has the Fed made any announcements this week?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "What's happening in the bond market?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "Any geopolitical news affecting markets?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "What's the dollar index doing?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "Any news on oil prices?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "What is the market saying about a recession?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "Is there a rotation to value stocks?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "Any big insider trades reported today?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "What are hedge funds buying right now?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "Any short squeeze candidates in news?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "China's economy impact on US stocks news"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "Any news on ETF flows?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "What happened to small caps today?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "Risk-off move happening in market news?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "Any news on FOMC minutes?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "whats moving the market today news"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "sp500 performance news"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "big market news today?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "rates and fed news"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "any catalyst for AAPL move today news?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "What is happening in crypto news?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    # ─────────────────────────────────────────────
    # No tool — Chitchat, Greetings, General Info (50)
    # ─────────────────────────────────────────────
    {
        "input": {"query": "Hello, how are you?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "What can you help me with?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Thanks!"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Good morning"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Who are you?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "What is your name?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "What are your capabilities?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Can you help me?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "How does this work?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Are you an AI?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "What is RSI?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Explain what ATR means"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "What is a limit order?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "How does dollar cost averaging work?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "What is a stop loss?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Explain portfolio diversification"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Difference between market and limit order?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "How do I calculate P&L?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "What does bearish mean?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "What is a bull market?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "What is an order?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Tell me about trade history in general"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "How do I read news?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "What is order flow?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Can you explain trade execution?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "What happened in 2008?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "How do stocks work?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "What is AAPL's business model?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Explain quantitative trading"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "What is a portfolio manager?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {"input": {"query": "ok"}, "output": {"tool_called": False, "tool_name": None}},
    {"input": {"query": "sure"}, "output": {"tool_called": False, "tool_name": None}},
    {"input": {"query": "yes"}, "output": {"tool_called": False, "tool_name": None}},
    {"input": {"query": "no"}, "output": {"tool_called": False, "tool_name": None}},
    {"input": {"query": "lol"}, "output": {"tool_called": False, "tool_name": None}},
    {"input": {"query": "nice"}, "output": {"tool_called": False, "tool_name": None}},
    {"input": {"query": "got it"}, "output": {"tool_called": False, "tool_name": None}},
    {"input": {"query": "hmm"}, "output": {"tool_called": False, "tool_name": None}},
    {
        "input": {"query": "interesting"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {"input": {"query": "I see"}, "output": {"tool_called": False, "tool_name": None}},
    {
        "input": {"query": "helo how r u"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "wats rsi"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "thx bye"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "How do options work?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "What is short selling?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Explain margin trading"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "What is a futures contract?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "How is P/E ratio calculated?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "What is alpha in trading?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "What does beta mean?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    # ─────────────────────────────────────────────
    # No tool — Clarify Cases (Missing Order ID) (50)
    # ─────────────────────────────────────────────
    {
        "input": {"query": "What is the status of my order?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Check my latest order"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Why was my last trade made?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Tell me about my trade"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "What happened to my order?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Explain my last trade"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Why was that trade made?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "What were the indicators for my trade?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Show me trade history"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "What trades have been made?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "I want to know about order status"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Why did you buy this stock for me?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Explain the logic of my order"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "What indicators triggered my buy?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Why did the system sell?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Show me details for my trade"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "What was the reasoning for my order?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Check order status please"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Why buy TSLA earlier?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Show rationale for my last trade"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Status of order?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Why sell AAPL just now?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Indicators for my buy?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "What signal triggered my order?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Explain recent trade reasoning"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Which order was just placed?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Order status update needed"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Why was the trade executed?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Show indicators for recent buy"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Logic behind the latest trade?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Can you check my order?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Why did we buy?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Reasoning for the trade?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "What triggered my last trade?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Show me my order logic"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "What indicators were used for my buy?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Why sell?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Explain my recent trade"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Order logic?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Why did the agent buy?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Check my trade status"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Why was that sell made?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Indicators for my sell?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Signal for the buy?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Reason for recent order?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Status of my trade?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Why did we enter this trade?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Logic behind order?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Why buy TSLA?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Show rationale for sell"},
        "output": {"tool_called": False, "tool_name": None},
    },
]

# Ensure we have exactly 200 cases
assert len(test_cases) == 200, f"Expected 200 test cases, got {len(test_cases)}"

# Create dataset in LangSmith
try:
    dataset_name = "agent-bot-langgraph-dataset"
    # Check if dataset exists, if not it will be created implicitly by create_examples or we can use create_dataset
    if not client.has_dataset(dataset_name=dataset_name):
        client.create_dataset(
            dataset_name=dataset_name,
            description="Tool call evaluation for RAG Chatbot",
        )

    client.create_examples(
        inputs=[e["input"] for e in test_cases],
        outputs=[e["output"] for e in test_cases],
        dataset_name=dataset_name,
    )

    logger.info("🌱 Seeding LangSmith Dataset for RAG Chatbot Tool Calls...")
    logger.info(f"✅ Added {len(test_cases)} examples to dataset '{dataset_name}'")
except Exception as e:
    logger.error(f"❌ Failed to seed dataset: {e}")
