"""
Redis Stream Helper - Check and push data to Redis Cloud streams
Usage:
    python -m app.scripts.redis_stream_helper --check       # Check stream status
    python -m app.scripts.redis_stream_helper --push        # Push sample data
    python -m app.scripts.redis_stream_helper --push --count 5  # Push 5 sample items
"""

import argparse
import json
import redis
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from app.core.config import env_config


def get_redis_client():
    """Connect to Redis Cloud."""
    client = redis.Redis(
        host=env_config.redis_host,
        port=env_config.redis_port,
        password=env_config.redis_password,
        decode_responses=True,
    )
    # Test connection
    client.ping()
    print(f"Connected to Redis Cloud: {env_config.redis_host}:{env_config.redis_port}")
    return client


def check_streams(client):
    """Check the status of all pipeline streams."""
    streams = [
        ("Reddit Stream (input)", env_config.redis_reddit_stream),
        ("Preprocessing Stream", env_config.redis_preproc_stream),
        ("Ticker Stream", env_config.redis_ticker_stream),
        ("Event Stream", env_config.redis_event_stream),
        ("Sentiment Stream", env_config.redis_sentiment_stream),
    ]

    print("\n" + "=" * 60)
    print("REDIS STREAM STATUS")
    print("=" * 60)

    for name, stream_key in streams:
        try:
            length = client.xlen(stream_key)
            print(f"\n{name}:")
            print(f"  Key: {stream_key}")
            print(f"  Items: {length}")

            if length > 0:
                # Show first and last item IDs
                first = client.xrange(stream_key, count=1)
                last = client.xrevrange(stream_key, count=1)
                if first:
                    print(f"  First ID: {first[0][0]}")
                if last:
                    print(f"  Last ID: {last[0][0]}")

                # Preview latest item
                if last:
                    data = last[0][1]
                    if 'data' in data:
                        try:
                            parsed = json.loads(data['data']) if isinstance(data['data'], str) else data['data']
                            title = parsed.get('Title', parsed.get('title', 'N/A'))[:50]
                            print(f"  Latest title: {title}...")
                        except:
                            print(f"  Latest data keys: {list(data.keys())}")
        except redis.exceptions.ResponseError as e:
            print(f"\n{name}:")
            print(f"  Key: {stream_key}")
            print(f"  Status: Does not exist or empty")

    print("\n" + "=" * 60)


def push_sample_data(client, count=3):
    """Push sample Reddit posts to the input stream."""
    sample_posts = [
        {
            "Post_ID": "sample_001",
            "Title": "NVDA crushing it! AI demand through the roof, bought more shares today",
            "Body": "Nvidia just reported amazing earnings. Revenue up 200% YoY from AI chip demand. Jensen is a genius. Diamond hands on this one. $NVDA to the moon!",
            "Author": "test_user_1",
            "Created_UTC": 1707400000,
            "URL": "https://reddit.com/r/wallstreetbets/sample_001",
            "subreddit": "wallstreetbets",
            "Upvotes": 1500,
            "Comments": 234
        },
        {
            "Post_ID": "sample_002",
            "Title": "Tesla price cuts are getting desperate - TSLA looking bearish",
            "Body": "Another round of price cuts from Tesla. Margins are getting crushed. Competition from BYD is real. Sold my position last week. This stock is going down.",
            "Author": "test_user_2",
            "Created_UTC": 1707400100,
            "URL": "https://reddit.com/r/stocks/sample_002",
            "subreddit": "stocks",
            "Upvotes": 890,
            "Comments": 156
        },
        {
            "Post_ID": "sample_003",
            "Title": "Apple and Microsoft both reporting next week - what are your plays?",
            "Body": "AAPL and MSFT earnings coming up. Apple services revenue should be strong but iPhone sales might disappoint. Microsoft Azure growth is the key metric to watch. I'm bullish on both long term.",
            "Author": "test_user_3",
            "Created_UTC": 1707400200,
            "URL": "https://reddit.com/r/investing/sample_003",
            "subreddit": "investing",
            "Upvotes": 567,
            "Comments": 89
        },
        {
            "Post_ID": "sample_004",
            "Title": "AMD vs Intel - clear winner emerging",
            "Body": "AMD continues to take market share from Intel. INTC is struggling with their manufacturing while AMD and NVDA are eating their lunch. Long AMD, avoid Intel.",
            "Author": "test_user_4",
            "Created_UTC": 1707400300,
            "URL": "https://reddit.com/r/wallstreetbets/sample_004",
            "subreddit": "wallstreetbets",
            "Upvotes": 1200,
            "Comments": 345
        },
        {
            "Post_ID": "sample_005",
            "Title": "Google Gemini launch - is GOOGL undervalued?",
            "Body": "Google finally launched Gemini and it's impressive. The stock is trading at a discount compared to other mega caps. Advertising revenue is stable and YouTube is growing. Buying more GOOGL.",
            "Author": "test_user_5",
            "Created_UTC": 1707400400,
            "URL": "https://reddit.com/r/stocks/sample_005",
            "subreddit": "stocks",
            "Upvotes": 678,
            "Comments": 123
        },
    ]

    stream_key = env_config.redis_reddit_stream
    print(f"\nPushing {count} sample posts to: {stream_key}")
    print("-" * 40)

    for i, post in enumerate(sample_posts[:count]):
        # Redis streams expect string values
        msg_id = client.xadd(stream_key, {"data": json.dumps(post)})
        print(f"  [{i+1}] Pushed: {post['Title'][:40]}...")
        print(f"      ID: {msg_id}")

    print("-" * 40)
    print(f"Done! Pushed {count} items to {stream_key}")
    print("\nRun the pipeline with: docker-compose up")


def read_latest(client, stream_key, count=3):
    """Read the latest items from a stream."""
    print(f"\nLatest {count} items from {stream_key}:")
    print("-" * 60)

    items = client.xrevrange(stream_key, count=count)
    for msg_id, data in items:
        print(f"\nID: {msg_id}")
        if 'data' in data:
            try:
                parsed = json.loads(data['data']) if isinstance(data['data'], str) else data['data']
                print(f"  Title: {parsed.get('Title', parsed.get('title', 'N/A'))}")
                print(f"  Subreddit: {parsed.get('subreddit', 'N/A')}")
            except:
                print(f"  Data: {str(data)[:100]}...")
        else:
            print(f"  Keys: {list(data.keys())}")


def main():
    parser = argparse.ArgumentParser(description="Redis Stream Helper")
    parser.add_argument("--check", action="store_true", help="Check stream status")
    parser.add_argument("--push", action="store_true", help="Push sample data")
    parser.add_argument("--count", type=int, default=3, help="Number of items to push (default: 3)")
    parser.add_argument("--read", type=str, help="Read latest from specific stream key")

    args = parser.parse_args()

    try:
        client = get_redis_client()

        if args.check:
            check_streams(client)
        elif args.push:
            push_sample_data(client, args.count)
        elif args.read:
            read_latest(client, args.read)
        else:
            # Default: check streams
            check_streams(client)

    except redis.exceptions.ConnectionError as e:
        print(f"ERROR: Could not connect to Redis Cloud")
        print(f"  Host: {env_config.redis_host}")
        print(f"  Port: {env_config.redis_port}")
        print(f"  Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
