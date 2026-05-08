#!/usr/bin/env python3
"""
Dev test runner for TradingWorkflow.

Usage:
    # Full workflow — fetch real signal from DB, run all nodes
    python test_scripts/run.py --signal-id <mongo_object_id>

    # Ticker bypass — skip lookup, inject synthetic signal, start from market_data
    python test_scripts/run.py --ticker NVDA
    python test_scripts/run.py --ticker NVDA --direction SELL
"""

import asyncio
import argparse
import os
import sys
from functools import partial

# Allow imports from the project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from langchain_perplexity import ChatPerplexity
from langgraph.graph import END, START, StateGraph

from app.core.config import env_config
from app.agents.state import AgentState, SignalData
from app.services.trading_workflow import TradingWorkflow
from app.agents.nodes import (
    node_decide_trade,
    node_execute_trade,
    node_fetch_market_data,
    node_risk_adjust_trade,
    node_trade_logging,
    node_profile_reasoning,
)
from app.agents.nodes.market_data import AssetNotTradableError


# ── Mock Redis ────────────────────────────────────────────────────────────────

class MockRedisService:
    """Stubs all Redis publish calls so trade_logging runs without real Redis."""

    async def publish_trade_noti(self, notifications):
        for n in (notifications or []):
            print(f"   [Mock Redis] 🔔 trade_noti: order_id={n.get('order_id')} user_id={n.get('user_id')}")

    async def publish_order_timestamp(self, news_id, ticker):
        print(f"   [Mock Redis] ⏱️  order_timestamp: news_id={news_id} ticker={ticker}")

    async def pipeline_counter(self):
        print("   [Mock Redis] 📊 pipeline_counter")


# ── Synthetic signal ──────────────────────────────────────────────────────────

def build_synthetic_signal(ticker: str, direction: str = "BUY") -> SignalData:
    return SignalData(
        id="dev-test-0000",
        ticker=ticker.upper(),
        rumor_summary=f"Synthetic dev signal for {ticker} — testing full pipeline",
        credibility="Medium",
        credibility_reason="Manually injected signal for local development testing",
        references=[],
        trade_signal=direction.upper(),
        confidence=0.75,
        trade_rationale=f"Dev test for {ticker} — validating {direction} signal path",
        position_size_pct=1.0,
        stop_loss_pct=8.0,
        target_pct=20.0,
        news_id="dev-news-0000",
    )


# ── Ticker-bypass workflow ────────────────────────────────────────────────────

class TickerTestWorkflow:
    """
    Same graph as TradingWorkflow but starts at fetch_market_data.
    Use this when you want to inject a ticker directly without a DB signal.
    """

    def __init__(self, llm_client, redis_service):
        self.llm = llm_client
        self.redis_service = redis_service
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(AgentState)

        reasoning_with_llm           = partial(node_decide_trade, self.llm)
        profile_reasoning_with_llm   = partial(node_profile_reasoning, self.llm)
        trade_logging_with_redis     = partial(node_trade_logging, self.redis_service)

        graph.add_node("fetch_market_data", node_fetch_market_data)
        graph.add_node("reasoning",         reasoning_with_llm)
        graph.add_node("risk_adjust",       node_risk_adjust_trade)
        graph.add_node("profile_reasoning", profile_reasoning_with_llm)
        graph.add_node("execute",           node_execute_trade)
        graph.add_node("trade_logging",     trade_logging_with_redis)

        graph.add_edge(START,               "fetch_market_data")
        graph.add_edge("fetch_market_data", "reasoning")
        graph.add_edge("reasoning",         "risk_adjust")
        graph.add_edge("risk_adjust",       "profile_reasoning")
        graph.add_conditional_edges(
            "profile_reasoning",
            lambda s: s.get("should_execute", False),
            {True: "execute", False: "trade_logging"},
        )
        graph.add_edge("execute",       "trade_logging")
        graph.add_edge("trade_logging", END)
        return graph.compile()

    async def run(self, signal_data: SignalData) -> dict:
        return await self.graph.ainvoke({
            "signal_id":   signal_data.id,
            "signal_data": signal_data,
        })


# ── Result summary ────────────────────────────────────────────────────────────

def print_summary(result: dict) -> None:
    SEP = "─" * 60
    print(f"\n{SEP}")
    print("  RESULT SUMMARY")
    print(SEP)

    signal: SignalData = result.get("signal_data")
    if signal:
        print(f"  Ticker        : {signal.ticker}")
        print(f"  Signal dir    : {signal.trade_signal}")

    order_details = result.get("order_details")
    if order_details:
        print(f"\n  ── Reasoning node ──")
        print(f"  Action        : {order_details.action}")
        print(f"  Confidence    : {order_details.confidence:.0%}")
        print(f"  Entry         : ${order_details.entry_price:.2f}")
        print(f"  Stop Loss     : ${order_details.stop_loss:.2f}")
        print(f"  Take Profit   : ${order_details.take_profit:.2f}")
        print(f"  Qty           : {order_details.qty}")
        print(f"  R:R           : {order_details.risk_reward}")
        print(f"  Price used    : ${order_details.current_stock_price:.2f}")

    order_list = result.get("order_list") or []
    print(f"\n  ── Orders built : {len(order_list)} ──")
    for i, o in enumerate(order_list, 1):
        adj     = o.get("adjusted_order_details")
        profile = o.get("profile")
        user_id = o.get("user_id", "?")
        profile_str = profile.value if hasattr(profile, "value") else str(profile)
        if adj:
            print(f"  [{i}] user={user_id} | profile={profile_str} | "
                  f"action={adj.action} | qty={adj.qty} | entry=${adj.entry_price:.2f} | "
                  f"sl=${adj.stop_loss:.2f} | tp=${adj.take_profit:.2f}")

    exec_results = result.get("execution_results") or []
    print(f"\n  ── Executions   : {len(exec_results)} ──")
    for r in exec_results:
        print(f"  status={r.get('status')} | user={r.get('user_id')} | order_id={r.get('order_id')}")

    print(f"\n  should_execute  : {result.get('should_execute', False)}")
    print(SEP + "\n")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="Dev test runner for TradingWorkflow")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--signal-id", metavar="ID",
        help="MongoDB ObjectId of an existing signal — runs the full workflow including lookup",
    )
    mode.add_argument(
        "--ticker", metavar="SYMBOL",
        help="Ticker symbol — bypasses lookup and injects a synthetic signal",
    )
    parser.add_argument(
        "--direction", default="BUY", choices=["BUY", "SELL", "NO_TRADE"],
        help="Trade direction for synthetic signal (default: BUY)",
    )
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  TRADING AGENT — DEV TEST RUN")
    print(f"  Service URL : {env_config.trading_service_url}")
    print(f"  LLM         : {env_config.perplexity_model}")
    print("=" * 60 + "\n")

    llm = ChatPerplexity(
        pplx_api_key=env_config.perplexity_api_key,
        model=env_config.perplexity_model or "sonar",
        temperature=float(env_config.perplexity_temperature or 0.2),
    )
    mock_redis = MockRedisService()

    try:
        if args.ticker:
            signal_data = build_synthetic_signal(args.ticker, args.direction)
            print(f"  Mode      : TICKER BYPASS")
            print(f"  Ticker    : {args.ticker.upper()} | Direction: {args.direction}\n")
            workflow = TickerTestWorkflow(llm_client=llm, redis_service=mock_redis)
            result = await workflow.run(signal_data)
        else:
            print(f"  Mode      : FULL WORKFLOW")
            print(f"  Signal ID : {args.signal_id}\n")
            workflow = TradingWorkflow(llm_client=llm, redis_service=mock_redis)
            result = await workflow.run({"signal_id": args.signal_id})

        print_summary(result)

    except AssetNotTradableError as e:
        print(f"\n⏭️  SKIPPED — {e}\n")
        sys.exit(0)
    except KeyboardInterrupt:
        print("\n⛔ Interrupted\n")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ ERROR — {e}\n")
        raise


if __name__ == "__main__":
    asyncio.run(main())
