"""
Seed script for populating the LangSmith 'ragbot-test-tools' dataset with
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
"""

import logging
import os

from app.core.config import env_config
from langsmith import Client

os.environ["LANGSMITH_API_KEY"] = env_config.langsmith_api_key
client = Client()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

test_cases = [
    # ─────────────────────────────────────────────
    # get_trade_history_details — clear cases (25)
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
    # ─────────────────────────────────────────────
    # get_trade_history_details — edge cases (20)
    # ─────────────────────────────────────────────
    {
        "input": {"query": "why this trade?", "order_id": "1234"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "what triggered it?", "order_id": "5678"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "reasoning?", "order_id": "9012"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "RSI for order #4321", "order_id": "4321"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "was this trade good?", "order_id": "1111"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "performance of order #2222", "order_id": "2222"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "Why did we do this?", "order_id": "3456"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "what was the logic", "order_id": "7654"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "explain", "order_id": "8888"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "technical analysis behind order #6543", "order_id": "6543"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "y did we buy tsla on order 999", "order_id": "999"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "explain trade #7777 plz", "order_id": "7777"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "order #1234 — why was it placed?", "order_id": "1234"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "for order #5678, what was the signal?", "order_id": "5678"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "what indicators for #6789?", "order_id": "6789"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "Hello! Also what is the RSI on order #9999?",
            "order_id": "9999",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "order #3456 reasoning", "order_id": "3456"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "what was the logic behind selling here",
            "order_id": "4321",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "trade details pls", "order_id": "5432"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "Thanks, now explain order #6666", "order_id": "6666"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    # ─────────────────────────────────────────────
    # get_general_news — clear cases (25)
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
        "input": {"query": "NVDA earnings report"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "AAPL stock news"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "TSLA analyst upgrades"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "MSFT quarterly results"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "AMD vs INTEL competition news"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    # ─────────────────────────────────────────────
    # get_general_news — edge cases (15)
    # ─────────────────────────────────────────────
    {
        "input": {"query": "news"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "market"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "AAPL?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "what's up with crypto?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "how is the market doing"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "TSLA news pls"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "what happened today in markets?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "give me market vibes"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "CPI data impact on stocks"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "nvda newss"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "aapl crashing why"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "Good morning, any NVDA news today?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "what's the vibe in markets rn"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "recession news"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "any updates on the market?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    # ─────────────────────────────────────────────
    # No tool — clear cases (20)
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
        "input": {
            "query": "What is the difference between a market order and limit order?"
        },
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
    # ─────────────────────────────────────────────
    # No tool — edge cases (30)
    # ─────────────────────────────────────────────
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
        "input": {"query": "What does beta mean for a stock?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    # ─────────────────────────────────────────────
    # No tool — no order_id, should ask user (15)
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
        "input": {"query": "What is the Sharpe ratio?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "How do I evaluate a trade?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "What makes a good entry point?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "Can you summarise what we talked about?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    {
        "input": {"query": "What did I ask you earlier?"},
        "output": {"tool_called": False, "tool_name": None},
    },
    # ─────────────────────────────────────────────
    # get_trade_history_details — additional cases (25)
    # ─────────────────────────────────────────────
    {
        "input": {
            "query": "What were the Bollinger Band conditions for order #1010?",
            "order_id": "1010",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "Did order #2020 use a trailing stop?", "order_id": "2020"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "What volume was recorded when order #3030 triggered?",
            "order_id": "3030",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "Was order #4040 a momentum or mean reversion trade?",
            "order_id": "4040",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "What was the MACD reading at time of order #5050?",
            "order_id": "5050",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "Was order #6060 triggered by an earnings event?",
            "order_id": "6060",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "Explain the risk/reward on order #7070",
            "order_id": "7070",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "What timeframe was used to analyse order #8080?",
            "order_id": "8080",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "What was the sector context when order #9090 was placed?",
            "order_id": "9090",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "Did order #1212 involve a breakout pattern?",
            "order_id": "1212",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "What was the conviction level behind order #2323?",
            "order_id": "2323",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "Was order #3434 part of a larger position sizing strategy?",
            "order_id": "3434",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "What news event triggered order #4545?",
            "order_id": "4545",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "How did market volatility affect order #5656?",
            "order_id": "5656",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "What was the drawdown on order #6767?", "order_id": "6767"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "Was order #7878 based on a bullish divergence?",
            "order_id": "7878",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "What was the target price for order #8989?",
            "order_id": "8989",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "Describe the setup that led to order #1313",
            "order_id": "1313",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "What chart pattern was identified for order #2424?",
            "order_id": "2424",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {
            "query": "How long was the position held in order #3535?",
            "order_id": "3535",
        },
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "wut happened with order 4646", "order_id": "4646"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "order 5757 — good or bad call?", "order_id": "5757"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "break it down for #6868", "order_id": "6868"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "analyse order #7979 for me", "order_id": "7979"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    {
        "input": {"query": "deep dive on order #8181", "order_id": "8181"},
        "output": {"tool_called": True, "tool_name": "get_trade_history_details"},
    },
    # ─────────────────────────────────────────────
    # get_general_news — additional cases (25)
    # ─────────────────────────────────────────────
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
        "input": {"query": "Is NVDA overbought based on recent news?"},
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
        "input": {"query": "What is the market saying about a potential recession?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "Is there a rotation from growth to value stocks?"},
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
        "input": {"query": "Any short squeeze candidates in the news?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "What's the latest on China's economy affecting US stocks?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "Any news on ETF flows this week?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "What happened to small cap stocks today?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "Is there a risk-off move happening in the market?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "Any news on FOMC minutes?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "whats moving the market today"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "sp500 news"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "big news today?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "rates news"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
    {
        "input": {"query": "any catalyst for AAPL move today?"},
        "output": {"tool_called": True, "tool_name": "get_general_news"},
    },
]

assert len(test_cases) == 200, f"Expected 200 test cases, got {len(test_cases)}"

client.create_examples(
    inputs=[e["input"] for e in test_cases],
    outputs=[e["output"] for e in test_cases],
    dataset_name="ragbot-test-tools",
)

logger = logging.getLogger("rag-chatbot")
logger.info("🌱 Seeding LangSmith Dataset for RAG Chatbot Tool Calls...")
logger.info(f"✅ Added {len(test_cases)} examples to dataset")
