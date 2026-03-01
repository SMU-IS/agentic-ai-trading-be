"""
Redis Stream Helper — Sentiment Analysis Service
=================================================
Usage:
    python -m app.scripts.redis_stream_helper --check
    python -m app.scripts.redis_stream_helper --read-event      [--count N]
    python -m app.scripts.redis_stream_helper --read-sentiment  [--count N]
"""

import argparse
import json
import sys
from pathlib import Path

import redis
from redis.exceptions import RedisError

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from app.core.config import env_config


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_redis_client() -> redis.Redis:
    client = redis.Redis(
        host=env_config.redis_host,
        port=env_config.redis_port,
        password=env_config.redis_password,
        decode_responses=True,
    )
    client.ping()
    print(f"Connected to Redis: {env_config.redis_host}:{env_config.redis_port}")
    return client


def deserialize(raw: dict) -> dict:
    """JSON-decode each field value (mirrors RedisStreamStorage.save() format)."""
    result = {}
    for k, v in raw.items():
        try:
            result[k] = json.loads(v)
        except (json.JSONDecodeError, TypeError):
            result[k] = v
    return result


def _truncate(text: str, length: int = 120) -> str:
    return text[:length] + "..." if len(text) > length else text


# ── Stream status ─────────────────────────────────────────────────────────────

def check_streams(client: redis.Redis):
    streams = [
        ("Event Stream (input)",    env_config.redis_event_stream),
        ("Sentiment Stream (output)", env_config.redis_sentiment_stream),
    ]

    print("\n" + "=" * 60)
    print("REDIS STREAM STATUS")
    print("=" * 60)

    for label, key in streams:
        try:
            length = client.xlen(key)
            print(f"\n{label}")
            print(f"  Key   : {key}")
            print(f"  Items : {length}")

            if length == 0:
                continue

            first = client.xrange(key, count=1)
            last  = client.xrevrange(key, count=1)

            if first:
                print(f"  First : {first[0][0]}")
            if last:
                print(f"  Last  : {last[0][0]}")

            # Brief preview of the most recent message
            if last:
                item = deserialize(last[0][1])
                print(f"  Latest post ID: {item.get('id', '—')}")

                content = item.get("content", {})
                text = content.get("clean_combined_withurl", "") if isinstance(content, dict) else ""
                if text:
                    print(f"  Text  : {_truncate(text, 80)}")

                tickers = list(item.get("ticker_metadata", {}).keys()) if item.get("ticker_metadata") else []
                if tickers:
                    print(f"  Tickers: {', '.join(tickers)}")

                sa = item.get("sentiment_analysis")
                if sa and isinstance(sa, dict) and sa.get("ticker_sentiments"):
                    labels = {
                        t: d.get("sentiment_label", "?")
                        for t, d in sa["ticker_sentiments"].items()
                    }
                    print(f"  Sentiment: {labels}")

        except RedisError as e:
            print(f"\n{label}")
            print(f"  Key   : {key}")
            print(f"  Status: Does not exist or empty ({e})")

    print("\n" + "=" * 60)


# ── Read event stream ─────────────────────────────────────────────────────────

def read_event_stream(client: redis.Redis, count: int = 3):
    key   = env_config.redis_event_stream
    items = client.xrevrange(key, count=count)

    print(f"\n{'=' * 60}")
    print(f"EVENT STREAM  [{key}]  — latest {count}")
    print(f"{'=' * 60}")

    if not items:
        print("  (empty)")
        return

    for msg_id, raw in items:
        item = deserialize(raw)

        print(f"\nMsg ID : {msg_id}")
        print(f"Post ID: {item.get('id', '—')}")
        print(f"Author : {item.get('Author', '—')}  "
              f"Subreddit: {item.get('subreddit', '—')}")

        content = item.get("content", {})
        if isinstance(content, dict):
            text = content.get("clean_combined_withurl", content.get("clean_combined", ""))
            if text:
                print(f"Text   : {_truncate(text)}")

        ticker_meta = item.get("ticker_metadata", {})
        if isinstance(ticker_meta, dict) and ticker_meta:
            print(f"Tickers: {', '.join(ticker_meta.keys())}")
            for ticker, info in ticker_meta.items():
                if isinstance(info, dict):
                    print(f"  {ticker}: {info.get('OfficialName', '—')}  "
                          f"[{info.get('event_type', '—')}]")

        print("-" * 60)


# ── Read sentiment stream ─────────────────────────────────────────────────────

def read_sentiment_stream(client: redis.Redis, count: int = 3):
    key   = env_config.redis_sentiment_stream
    items = client.xrevrange(key, count=count)

    print(f"\n{'=' * 60}")
    print(f"SENTIMENT STREAM  [{key}]  — latest {count}")
    print(f"{'=' * 60}")

    if not items:
        print("  (empty)")
        return

    for msg_id, raw in items:
        item = deserialize(raw)

        print(f"\nMsg ID : {msg_id}")
        print(f"Post ID: {item.get('id', '—')}")

        content = item.get("content", {})
        if isinstance(content, dict):
            text = content.get("clean_combined_withurl", content.get("clean_combined", ""))
            if text:
                print(f"Text   : {_truncate(text)}")

        sa = item.get("sentiment_analysis", {})
        if not isinstance(sa, dict):
            print("Sentiment: (none)")
            print("-" * 60)
            continue

        if sa.get("error"):
            print(f"Error  : {sa['error']}")
            print("-" * 60)
            continue

        print(f"Success: {sa.get('analysis_successful', '—')}")

        ticker_sentiments = sa.get("ticker_sentiments", {})
        if isinstance(ticker_sentiments, dict):
            for ticker, data in ticker_sentiments.items():
                if not isinstance(data, dict):
                    continue
                score  = data.get("sentiment_score", 0.0)
                label  = data.get("sentiment_label", "—").upper()
                name   = data.get("official_name", ticker)
                reason = data.get("reasoning", "")
                fb     = data.get("factor_breakdown", {})

                print(f"\n  {ticker} ({name})")
                print(f"    Score  : {score:+.4f}  [{label}]")
                if isinstance(fb, dict):
                    print(f"    Factors: MI={fb.get('market_impact', 0):.3f}  "
                          f"T={fb.get('tone', 0):.3f}  "
                          f"SQ={fb.get('source_quality', 0):.3f}  "
                          f"C={fb.get('context', 0):.3f}")
                if reason:
                    print(f"    Reason : {_truncate(reason, 100)}")

        print("-" * 60)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Redis Stream Helper — Sentiment Analysis Service"
    )
    parser.add_argument("--check",          action="store_true",
                        help="Show stream status summary (default)")
    parser.add_argument("--read-event",     action="store_true",
                        help="Read latest messages from event_stream")
    parser.add_argument("--read-sentiment", action="store_true",
                        help="Read latest messages from sentiment_stream")
    parser.add_argument("--count", type=int, default=3,
                        help="Number of messages to read (default: 3)")
    args = parser.parse_args()

    try:
        client = get_redis_client()

        if args.read_event:
            read_event_stream(client, args.count)
        elif args.read_sentiment:
            read_sentiment_stream(client, args.count)
        else:
            check_streams(client)

    except redis.exceptions.ConnectionError as e:
        print(f"ERROR: Could not connect ({env_config.redis_host}:{env_config.redis_port})")
        print(f"  {e}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
