"""
Diagnostic script — finds posts with:
  1. posted_timestamp > scraped_timestamp  (scraper records post as scraped before it was posted)
  2. ticker_timestamp < ticker_timestamp_start  (ticker end before start)

Run from metrics-tracker/:
    python check_latency_bugs.py
"""

import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from redis.asyncio import Redis
from app.core.config import env_config


redis_client = Redis(
    host=env_config.redis_host,
    port=env_config.redis_port,
    password=env_config.redis_password,
    decode_responses=True,
)


def _parse_dt(val: str) -> datetime | None:
    if not val:
        return None
    try:
        dt = datetime.fromisoformat(val)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("Asia/Singapore"))
        return dt
    except ValueError:
        return None


async def check():
    posted_after_scraped = []
    ticker_end_before_start = []

    cursor = 0
    total = 0
    while True:
        cursor, keys = await redis_client.scan(cursor, match="post_timestamps:*", count=100)

        if keys:
            pipe = redis_client.pipeline()
            for key in keys:
                pipe.hgetall(key)
            results = await pipe.execute()

            for key, data in zip(keys, results):
                total += 1

                posted   = _parse_dt(data.get("posted_timestamp"))
                scraped  = _parse_dt(data.get("scraped_timestamp"))
                tk_start = _parse_dt(data.get("ticker_timestamp_start"))
                tk_end   = _parse_dt(data.get("ticker_timestamp"))

                if posted and scraped and posted > scraped:
                    diff_s = (posted - scraped).total_seconds()
                    posted_after_scraped.append({
                        "key": key,
                        "posted":  data.get("posted_timestamp"),
                        "scraped": data.get("scraped_timestamp"),
                        "diff_s":  round(diff_s, 3),
                    })

                if tk_start and tk_end and tk_end < tk_start:
                    diff_s = (tk_end - tk_start).total_seconds()
                    ticker_end_before_start.append({
                        "key":      key,
                        "tk_start": data.get("ticker_timestamp_start"),
                        "tk_end":   data.get("ticker_timestamp"),
                        "diff_s":   round(diff_s, 3),
                    })

        if cursor == 0:
            break

    print(f"\nScanned {total} keys\n")

    print(f"=== posted > scraped: {len(posted_after_scraped)} cases ===")
    for r in sorted(posted_after_scraped, key=lambda x: x["diff_s"], reverse=True)[:10]:
        print(f"  {r['key']}")
        print(f"    posted:  {r['posted']}")
        print(f"    scraped: {r['scraped']}")
        print(f"    diff:    +{r['diff_s']}s")

    print(f"\n=== ticker_end < ticker_start: {len(ticker_end_before_start)} cases ===")
    for r in sorted(ticker_end_before_start, key=lambda x: x["diff_s"])[:10]:
        print(f"  {r['key']}")
        print(f"    start: {r['tk_start']}")
        print(f"    end:   {r['tk_end']}")
        print(f"    diff:  {r['diff_s']}s")

    await redis_client.aclose()


if __name__ == "__main__":
    asyncio.run(check())
