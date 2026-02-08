#!/usr/bin/env python3
# test_trading_workflow_ollama.py
#
import asyncio
import json

from langchain_ollama import ChatOllama

from app.services.trading_workflow import TradingWorkflow

async def main():
    ollama = ChatOllama(
        model="llama3.1:latest",
        temperature=0.1,
        base_url="http://localhost:11434",
    )

    workflow = TradingWorkflow(llm_client=ollama)

    # Test cases
    test_cases = [
        {
            "ticker": "AAPL",
            "signal": {
                "sentiment": "bearish",
                "score": -0.75,
                "event_type": "earnings_miss",
            },
        }
    ]

    print("=== Testing TradingWorkflow with Ollama ===\n")

    for i, input_data in enumerate(test_cases, 1):
        print(
            f"🧪 Test Case {i}: {input_data['ticker']} ({input_data['signal']['sentiment']})"
        )
        print("-" * 60)

        result = await workflow.run(input_data)

        # print("📊 Final Result:")
        # print(f"  Action: {result.get('action', 'N/A')}")
        # print(f"  Should Execute: {result.get('should_execute', 'N/A')}")
        # print(f"  Order Details: {result.get('order_details', 'N/A')}")
        # print(f"  Reasoning: {result.get('reasoning', 'N/A')}")
        # print("\n" + "=" * 60 + "\n")

    print("🎉 All tests complete!")
    await asyncio.sleep(0.1)

    workflow.export_graph()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Error: {e}")
