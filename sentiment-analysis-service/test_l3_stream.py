"""
L3 End-to-End Stream Test for Sentiment Analysis Service
=========================================================

Tests the full Redis stream pipeline:
  1. Push a test item to event_stream
  2. Wait for the worker to process it
  3. Read the result from sentiment_stream
  4. Print the sentiment output

Usage:
  python test_l3_stream.py

Requires:
  - Docker containers running: docker-compose up -d
  - .env file in this directory with Redis + Groq credentials
"""

import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path

import redis.asyncio as redis
from dotenv import load_dotenv

# ── Load env ──────────────────────────────────────────────────────────────────

load_dotenv(Path(__file__).parent / ".env")

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
EVENT_STREAM = os.getenv("EVENT_STREAM", "event_stream")
SENTIMENT_STREAM = os.getenv("SENTIMENT_STREAM", "sentiment_stream")

# ── Test payload ──────────────────────────────────────────────────────────────

# Use a unique ID each run to avoid dedup collisions
TEST_POST_ID = f"l3_test_{uuid.uuid4().hex[:8]}"

TEST_ITEM = {
    "id": TEST_POST_ID,
    "content": {
        "clean_combined_withurl": (
            "Microsoft reported strong Q3 earnings, beating analyst expectations "
            "with revenue of $61.9B, driven by Azure cloud growth of 21%. "
            "The company also announced a new AI-powered Copilot feature for Office 365. "
            "Analysts raised price targets, with some forecasting MSFT could reach $500 "
            "within 12 months. Google (GOOGL) also beat expectations, but faces ongoing "
            "antitrust scrutiny. Costco (COST) saw flat revenue growth and is trading "
            "at 50x earnings, which some consider overvalued."
        )
    },
    "ticker_metadata": {
        "MSFT": {"OfficialName": "Microsoft Corporation", "event_type": "EARNINGS"},
        "GOOGL": {"OfficialName": "Alphabet Inc.", "event_type": "REGULATORY"},
        "COST": {"OfficialName": "Costco Wholesale Corporation", "event_type": "INVESTOR_OPINION"},
    },
    "subreddit": "wallstreetbets",
    "Author": "test_user",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

async def push_to_event_stream(r: redis.Redis) -> str:
    """Push test item to event_stream (mimics upstream service format)."""
    # Each field is individually JSON-serialized (matches RedisStreamStorage.save())
    stream_fields = {k: json.dumps(v) for k, v in TEST_ITEM.items()}
    msg_id = await r.xadd(EVENT_STREAM, stream_fields)
    return msg_id


async def poll_sentiment_stream(r: redis.Redis, timeout_sec: int = 120) -> dict | None:
    """
    Poll sentiment_stream for a message with our test post ID.
    Reads from $ (new messages only) with short blocking reads.
    """
    # Start reading from now (only new messages)
    last_id = "$"
    deadline = time.monotonic() + timeout_sec

    print(f"  Polling {SENTIMENT_STREAM} for post ID: {TEST_POST_ID}")
    print(f"  Timeout: {timeout_sec}s", flush=True)

    while time.monotonic() < deadline:
        entries = await r.xread({SENTIMENT_STREAM: last_id}, count=10, block=3000)

        if not entries:
            remaining = int(deadline - time.monotonic())
            print(f"  ... waiting ({remaining}s remaining)", flush=True)
            continue

        for _, messages in entries:
            for msg_id, raw_data in messages:
                last_id = msg_id

                # Deserialize each field
                item = {}
                for k, v in raw_data.items():
                    try:
                        item[k] = json.loads(v)
                    except (json.JSONDecodeError, TypeError):
                        item[k] = v

                if item.get("id") == TEST_POST_ID:
                    return item

    return None


def print_result(item: dict):
    """Pretty-print the sentiment result."""
    print("\n" + "=" * 70)
    print("SENTIMENT RESULT")
    print("=" * 70)
    print(f"Post ID : {item.get('id')}")

    sa = item.get("sentiment_analysis", {})
    print(f"Success : {sa.get('analysis_successful')}")
    if sa.get("error"):
        print(f"Error   : {sa.get('error')}")

    ticker_sentiments = sa.get("ticker_sentiments", {})
    if ticker_sentiments:
        print("\nPer-Ticker Sentiment:")
        for ticker, data in ticker_sentiments.items():
            score = data.get("sentiment_score", 0.0)
            label = data.get("sentiment_label", "?")
            name = data.get("official_name", ticker)
            reasoning = data.get("reasoning", "")
            fb = data.get("factor_breakdown", {})
            print(f"\n  {ticker} ({name})")
            print(f"    Score  : {score:+.4f}  [{label.upper()}]")
            print(f"    Factors: MI={fb.get('market_impact', 0):.3f}  "
                  f"T={fb.get('tone', 0):.3f}  "
                  f"SQ={fb.get('source_quality', 0):.3f}  "
                  f"CN={fb.get('context', 0):.3f}")
            print(f"    Reason : {reasoning[:120]}")

    print("=" * 70)


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    print("=" * 70)
    print("L3 END-TO-END STREAM TEST — Sentiment Analysis Service")
    print("=" * 70)
    print(f"\nRedis  : {REDIS_HOST}:{REDIS_PORT}")
    print(f"Input  : {EVENT_STREAM}")
    print(f"Output : {SENTIMENT_STREAM}")
    print(f"Post ID: {TEST_POST_ID}\n")

    r = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        decode_responses=True,
    )

    try:
        # 1. Verify Redis connection
        await r.ping()
        print("✅ Redis connected")

        # 2. Check worker is alive (optional — proceed either way)
        heartbeat_keys = []
        cursor = 0
        while True:
            cursor, keys = await r.scan(cursor=cursor, match="sentiment_analysis:heartbeat:*", count=100)
            heartbeat_keys.extend(keys)
            if cursor == 0:
                break

        if heartbeat_keys:
            print(f"✅ Worker heartbeat detected: {heartbeat_keys}")
        else:
            print("⚠️  No worker heartbeat found — ensure worker container is running")
            print("   Run: docker-compose up -d sentiment-analysis-worker")
            print("   Continuing anyway (worker may still be starting up)...\n")

        # 3. Push test message to event_stream
        msg_id = await push_to_event_stream(r)
        print(f"✅ Pushed test item to {EVENT_STREAM} (stream msg ID: {msg_id})")

        # 4. Poll sentiment_stream for result
        print(f"\n⏳ Waiting for worker to process and write to {SENTIMENT_STREAM}...")
        result = await poll_sentiment_stream(r, timeout_sec=120)

        # 5. Show result
        if result:
            print("\n✅ Result received!")
            print_result(result)
        else:
            print("\n❌ Timed out — no result received within 120 seconds")
            print("Check worker logs: docker logs sentiment-analysis-worker-container")
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        raise

    finally:
        await r.aclose()


if __name__ == "__main__":
    asyncio.run(main())
