"""
Redis Stream Helper - Check and push data to Redis Cloud streams
Usage:
    python -m app.scripts.redis_stream_helper --check       # Check stream status
    python -m app.scripts.redis_stream_helper --extract     # Extract 250 unique posts from preprocessing stream
    python -m app.scripts.redis_stream_helper --extract --count 150 --output my_posts.json
    python -m app.scripts.redis_stream_helper --extract --exclude reddit_preprocessed.json 50_tickers_output.json  # excludes by filename
"""

import argparse
import json
import sys
from pathlib import Path

import redis
from redis.exceptions import RedisError

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
                    if "data" in data:
                        try:
                            parsed = (
                                json.loads(data["data"])
                                if isinstance(data["data"], str)
                                else data["data"]
                            )
                            title = parsed.get("Title", parsed.get("title", "N/A"))[:50]
                            print(f"  Latest title: {title}...")
                        except Exception as e:
                            print(f"  Latest data keys: {list(data.keys())} {e}")
        except RedisError:
            print(f"\n{name}:")
            print(f"  Key: {stream_key}")
            print("  Status: Does not exist or empty")

    print("\n" + "=" * 60)


def read_latest(client, stream_key, count=3):
    """Read the latest items from a stream."""
    print(f"\nLatest {count} items from {stream_key}:")
    print("-" * 60)

    items = client.xrevrange(stream_key, count=count)
    for msg_id, data in items:
        print(f"\nID: {msg_id}")
        if "data" in data:
            try:
                parsed = (
                    json.loads(data["data"])
                    if isinstance(data["data"], str)
                    else data["data"]
                )
                print(f"  Title: {parsed.get('Title', parsed.get('title', 'N/A'))}")
                print(f"  Subreddit: {parsed.get('subreddit', 'N/A')}")
            except Exception as e:
                print(f"  Data: {str(data)[:100]} Error ${e}...")
        else:
            print(f"  Keys: {list(data.keys())}")


def load_existing_ids(exclude_files):
    """Load IDs from existing JSON files to exclude from extraction."""
    existing_ids = set()
    for filepath in exclude_files:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            file_ids = {item.get("id") for item in data if item.get("id")}
            print(f"  Loaded {len(file_ids)} IDs from: {filepath}")
            existing_ids.update(file_ids)
        except FileNotFoundError:
            print(f"  WARNING: File not found, skipping: {filepath}")
        except (json.JSONDecodeError, TypeError) as e:
            print(f"  WARNING: Could not parse {filepath}: {e}")
    return existing_ids


def extract_unique_posts(
    client, count=250, output_file="extracted_posts.json", exclude_files=None
):
    """Extract unique posts from the preprocessing stream and save to JSON.

    Skips posts whose IDs already exist in any of the exclude_files.
    """
    stream_key = env_config.redis_preproc_stream
    print(f"\nExtracting up to {count} unique posts from: {stream_key}")
    print("-" * 60)

    # Load IDs to exclude from existing annotated files
    seen_ids = set()
    if exclude_files:
        print("Loading existing IDs to exclude:")
        seen_ids = load_existing_ids(exclude_files)
        print(f"  Total IDs to exclude: {len(seen_ids)}")
        print()

    total_in_stream = client.xlen(stream_key)
    print(f"Total items in stream: {total_in_stream}")

    # Read all entries from the stream in batches
    unique_posts = []
    last_id = "0-0"
    batch_size = 500
    skipped_duplicates = 0

    while len(unique_posts) < count:
        entries = client.xrange(stream_key, min=last_id, count=batch_size)
        if not entries:
            break

        for msg_id, data in entries:
            last_id = msg_id

            # Handle two stream formats:
            # 1) Flat key-value pairs (id, content_type, etc. at top level)
            # 2) Nested inside a "data" key as JSON string
            if "data" in data and len(data) == 1:
                try:
                    parsed = (
                        json.loads(data["data"])
                        if isinstance(data["data"], str)
                        else data["data"]
                    )
                except (json.JSONDecodeError, TypeError):
                    continue
            else:
                # Flat format — strip extra quotes from values and parse JSON fields
                parsed = {}
                for key, value in data.items():
                    if isinstance(value, str) and value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    if isinstance(value, str) and (value.startswith('{') or value.startswith('[')):
                        try:
                            value = json.loads(value)
                        except (json.JSONDecodeError, TypeError):
                            pass
                    parsed[key] = value

            post_id = parsed.get("id")
            if not post_id or post_id in seen_ids:
                if post_id in seen_ids:
                    skipped_duplicates += 1
                continue

            seen_ids.add(post_id)
            unique_posts.append(parsed)

            if len(unique_posts) >= count:
                break

        # Increment last_id to avoid re-reading the same entry
        # Redis stream IDs are "timestamp-sequence", increment sequence
        parts = last_id.split("-")
        last_id = f"{parts[0]}-{int(parts[1]) + 1}"

    print(f"Skipped {skipped_duplicates} posts already in exclude files")
    print(f"Extracted {len(unique_posts)} new unique posts")

    # Save to JSON file
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(unique_posts, f, indent=2, ensure_ascii=False)

    print(f"Saved to: {output_file}")
    print("-" * 60)

    # Preview first few posts
    for i, post in enumerate(unique_posts[:3]):
        title = post.get("content", {}).get("title", post.get("title", "N/A"))
        print(f"  [{i + 1}] {post.get('id', 'N/A')} - {title[:60]}")

    if len(unique_posts) > 3:
        print(f"  ... and {len(unique_posts) - 3} more")


def main():
    parser = argparse.ArgumentParser(description="Redis Stream Helper")
    parser.add_argument("--check", action="store_true", help="Check stream status")
    parser.add_argument("--push", action="store_true", help="Push sample data")
    parser.add_argument(
        "--count", type=int, default=None,
        help="Number of items (default: 3 for push, 250 for extract)"
    )
    parser.add_argument("--read", type=str, help="Read latest from specific stream key")
    parser.add_argument(
        "--extract", action="store_true",
        help="Extract unique posts from preprocessing stream to JSON"
    )
    parser.add_argument(
        "--output", type=str, default="extracted_posts.json",
        help="Output file path for extracted posts (default: extracted_posts.json)"
    )
    parser.add_argument(
        "--exclude", type=str, nargs="+",
        help="JSON filenames to exclude by ID (resolved relative to --exclude-dir)"
    )
    parser.add_argument(
        "--exclude-dir", type=str,
        default=r"C:\Users\school\OneDrive - Singapore Management University\Year 4 Sem 2\4. IS484 - Project Experience (FinTech)",
        help="Directory containing exclude files (default: IS484 project folder)"
    )

    args = parser.parse_args()

    # Resolve exclude filenames to full paths using exclude_dir
    exclude_files = None
    if args.exclude:
        exclude_dir = Path(args.exclude_dir)
        exclude_files = [
            str(exclude_dir / f) if not Path(f).is_absolute() else f
            for f in args.exclude
        ]

    try:
        client = get_redis_client()

        if args.check:
            check_streams(client)
        elif args.extract:
            extract_unique_posts(
                client,
                count=args.count or 250,
                output_file=args.output,
                exclude_files=exclude_files,
            )
        elif args.read:
            read_latest(client, args.read)
        else:
            # Default: check streams
            check_streams(client)

    except redis.exceptions.ConnectionError as e:
        print("ERROR: Could not connect to Redis Cloud")
        print(f"  Host: {env_config.redis_host}")
        print(f"  Port: {env_config.redis_port}")
        print(f"  Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
