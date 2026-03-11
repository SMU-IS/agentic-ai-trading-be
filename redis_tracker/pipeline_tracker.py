import redis
from collections import defaultdict
import os
from dotenv import load_dotenv

load_dotenv()

REDIS_HOST = os.getenv('REDIS_HOST', "")
REDIS_PORT = os.getenv('REDIS_PORT', 1234)
REDIS_DB = 0
REDIS_PASS = os.getenv('REDIS_PASS', "")

KEY_PATTERN = "post_timestamps:reddit:*"


def main():
    print(REDIS_HOST, REDIS_PORT, REDIS_PASS)
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, password=REDIS_PASS, decode_responses=True)

    counts = defaultdict(int)
    completed_orders = []
    cursor = 0

    while True:
        cursor, keys = r.scan(cursor=cursor, match=KEY_PATTERN, count=100)

        for key in keys:
            data = r.hgetall(key)
            has_order_timestamp = False
            for field, value in data.items():
                if not value:
                    continue

                # Treat ticker-specific stages separately
                if field.startswith("signal_timestamp"):
                    counts["signal_timestamp"] += 1

                elif field.startswith("order_timestamp"):
                    counts["order_timestamp"] += 1
                    has_order_timestamp = True

                elif field == "scraped_timestamp":
                    counts["scraped_timestamp"] += 1

                elif field == "vectorised_timestamp":
                    counts["vectorised_timestamp"] += 1
            
            if has_order_timestamp:
                completed_orders.append({
                    "key": key,
                    "fields": data
                })

        if cursor == 0:
            break

    print("\nPipeline Stage Counts")
    print("----------------------")

    for stage in [
        "scraped_timestamp",
        "vectorised_timestamp",
        "signal_timestamp",
        "order_timestamp",
    ]:
        print(f"{stage}: {counts[stage]}")
    
    print("\nKeys With Orders")
    print("----------------------")

    for item in completed_orders:
        print(f"\nKey: {item['key']}")
        for f, v in item["fields"].items():
            print(f"  {f}: {v}")


if __name__ == "__main__":
    main()