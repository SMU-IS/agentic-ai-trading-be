#!/usr/bin/env python3
# test_trading_workflow_ollama.py
#
import asyncio
import json

from langchain_ollama import ChatOllama

from app.services.trading_workflow import TradingWorkflow


class MockBroker:
    """Simple mock broker that just logs orders."""

    def place_order(self, *args, **kwargs):
        print(
            "[MockBroker] place_order called:",
            json.dumps({"args": args, "kwargs": kwargs}, indent=2),
        )


async def main():
    ollama = ChatOllama(
        model="llama3.1",
        temperature=0.1,
        base_url="http://localhost:11434",
    )

    broker_client = MockBroker()
    workflow = TradingWorkflow(llm_client=ollama, broker_client=broker_client)

    # Test cases
    test_cases = [
        # {
        #     "user_id": "joshua_123",
        #     "ticker": "AAPL",
        #     "signal": {"sentiment": "bullish", "score": 0.95},
        #     "portfolio": {"qty": 10, "avg_price": 150.0},
        #     "risk_profile": "aggressive",
        #     "query_vector": [0.0] * 10,
        # },
        # {
        #     "user_id": "joshua_123",
        #     "ticker": "AAPL",
        #     "signal": {"sentiment": "bearish", "score": 0.2},
        #     "portfolio": {"qty": 10, "avg_price": 150.0},
        #     "risk_profile": "aggressive",
        #     "query_vector": [0.0] * 10,
        # },
        # {
        #     "user_id": "joshua_123",
        #     "ticker": "AAPL",
        #     "signal": {"sentiment": "neutral", "score": 0.5},
        #     "portfolio": {"qty": 0, "avg_price": 0.0},
        #     "risk_profile": "conservative",
        #     "query_vector": [0.0] * 10,
        # },
        {
            "user_id": "joshua_123",
            "ticker": "AAPL",
            "signal": {
                "sentiment": "bearish",
                "score": -0.75,
                "event_type": "earnings_miss",
                "current_price": 145.0,
                "atr": 4.2,  # 14-period ATR
            },
            "portfolio": {"qty": 10, "avg_price": 150.0},
            "risk_profile": "aggressive",
            "query_vector": [0.0] * 10,
        }
    ]

    print("=== Testing TradingWorkflow with Ollama ===\n")

    for i, input_data in enumerate(test_cases, 1):
        print(
            f"🧪 Test Case {i}: {input_data['ticker']} ({input_data['signal']['sentiment']})"
        )
        print("-" * 60)

        result = await workflow.run(input_data)

        print("📊 Final Result:")
        print(f"  Action: {result.get('action', 'N/A')}")
        print(f"  Should Execute: {result.get('should_execute', 'N/A')}")
        print(f"  Order Details: {result.get('order_details', 'N/A')}")
        print(f"  Reasoning: {result.get('reasoning', 'N/A')}")
        print("\n" + "=" * 60 + "\n")

    print("🎉 All tests complete!")
    await asyncio.sleep(0.1)

    workflow.export_graph()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Error: {e}")
