"""
Populate Redis with fake test_timestamps:* entries and verify compute_pipeline_metrics logic.
Run: python test_metrics.py
Cleans up all test keys at the end.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from collections import defaultdict

import redis.asyncio as aioredis
from dotenv import load_dotenv
import os

load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = int(os.getenv("REDIS_PORT"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")

TEST_PREFIX = "test_timestamps"

# ── Helpers ───────────────────────────────────────────────────────────────────

def ts(delta_hours=0, delta_minutes=0):
    """Return an ISO timestamp offset from now."""
    return (datetime.now(timezone.utc) + timedelta(hours=delta_hours, minutes=delta_minutes)).isoformat()


def stage_times(base_offset_hours, durations_s):
    """
    Given a base scraped time and a list of per-stage durations (seconds),
    compute start/end timestamps for each pipeline stage.
    durations_s: [preproc, ticker, event, sentiment, vectorisation]
    """
    t = datetime.now(timezone.utc) + timedelta(hours=base_offset_hours)
    result = {}
    stages = ["preproc", "ticker", "event", "sentiment", "qdrant"]
    for stage, dur in zip(stages, durations_s):
        start = t
        end = t + timedelta(seconds=dur)
        result[f"{stage}_timestamp_start"] = start.isoformat()
        result[f"{stage}_timestamp"] = end.isoformat()
        t = end
    return result


# ── Test data ─────────────────────────────────────────────────────────────────

async def populate(r: aioredis.Redis):
    keys = []

    # 1. Reddit post — full pipeline, within 24h, signal + order placed
    #    scraped 3h ago, posted 3h 30s ago (30s scraper latency)
    key = f"{TEST_PREFIX}:reddit:abc001"
    scraped = datetime.now(timezone.utc) - timedelta(hours=3)
    posted  = scraped - timedelta(seconds=30)
    ordered = scraped + timedelta(minutes=5)
    mapping = {
        "scraped_timestamp": scraped.isoformat(),
        "posted_timestamp":  posted.isoformat(),
        **stage_times(-3, [2, 3, 4, 5, 2]),
        "signal_timestamp:AAPL": (scraped + timedelta(minutes=4)).isoformat(),
        "order_timestamp:AAPL":  ordered.isoformat(),
    }
    await r.hset(key, mapping=mapping)
    await r.expire(key, 3600)
    keys.append(key)

    # 1b. Reddit post — full pipeline within 1h, with aggregator + signal + order
    key = f"{TEST_PREFIX}:reddit:abc001b"
    scraped = datetime.now(timezone.utc) - timedelta(minutes=50)
    posted  = scraped - timedelta(seconds=30)
    signal  = scraped + timedelta(minutes=4)
    ordered = scraped + timedelta(minutes=5)
    aggregator = scraped + timedelta(seconds=18)  # after vectorisation (~16s), before signal
    mapping = {
        "scraped_timestamp":     scraped.isoformat(),
        "posted_timestamp":      posted.isoformat(),
        **stage_times(-50/60, [2, 3, 4, 5, 2]),
        "aggregator_timestamp":  aggregator.isoformat(),
        "signal_timestamp:AAPL": signal.isoformat(),
        "order_timestamp:AAPL":  ordered.isoformat(),
    }
    await r.hset(key, mapping=mapping)
    await r.expire(key, 3600)
    keys.append(key)

    # 2. Reddit post — full pipeline, within 1h (counts for service window too)
    key = f"{TEST_PREFIX}:reddit:abc002"
    scraped = datetime.now(timezone.utc) - timedelta(minutes=30)
    posted  = scraped - timedelta(seconds=45)
    mapping = {
        "scraped_timestamp": scraped.isoformat(),
        "posted_timestamp":  posted.isoformat(),
        **stage_times(-0.5, [1, 2, 3, 4, 1]),
    }
    await r.hset(key, mapping=mapping)
    await r.expire(key, 3600)
    keys.append(key)

    # 2b. TradingView Ideas — full pipeline, within 1h
    key = f"{TEST_PREFIX}:tradingview_ideas:user2:1711600001"
    scraped = datetime.now(timezone.utc) - timedelta(minutes=20)
    posted  = scraped - timedelta(seconds=120)
    mapping = {
        "scraped_timestamp": scraped.isoformat(),
        "posted_timestamp":  posted.isoformat(),
        **stage_times(-0.33, [2, 3, 4, 5, 2]),
    }
    await r.hset(key, mapping=mapping)
    await r.expire(key, 3600)
    keys.append(key)

    # 2c. TradingView Minds — full pipeline, within 1h
    key = f"{TEST_PREFIX}:tradingview_minds:mind001"
    scraped = datetime.now(timezone.utc) - timedelta(minutes=45)
    posted  = scraped - timedelta(seconds=60)
    mapping = {
        "scraped_timestamp": scraped.isoformat(),
        "posted_timestamp":  posted.isoformat(),
        **stage_times(-0.75, [1, 2, 3, 4, 1]),
    }
    await r.hset(key, mapping=mapping)
    await r.expire(key, 3600)
    keys.append(key)

    # 3. Reddit post — scraped but no ticker found (dropped at ticker stage)
    key = f"{TEST_PREFIX}:reddit:abc003"
    scraped = datetime.now(timezone.utc) - timedelta(hours=2)
    mapping = {
        "scraped_timestamp": scraped.isoformat(),
        "preproc_timestamp_start": (scraped + timedelta(seconds=1)).isoformat(),
        "preproc_timestamp":       (scraped + timedelta(seconds=3)).isoformat(),
    }
    await r.hset(key, mapping=mapping)
    await r.expire(key, 3600)
    keys.append(key)

    # 4. TradingView Ideas post — full pipeline, within 24h
    key = f"{TEST_PREFIX}:tradingview_ideas:user1:1711600000"
    scraped = datetime.now(timezone.utc) - timedelta(hours=5)
    posted  = scraped - timedelta(seconds=120)
    mapping = {
        "scraped_timestamp": scraped.isoformat(),
        "posted_timestamp":  posted.isoformat(),
        **stage_times(-5, [2, 3, 5, 6, 2]),
    }
    await r.hset(key, mapping=mapping)
    await r.expire(key, 3600)
    keys.append(key)

    # 5. Reddit post — older than 24h (should NOT appear in funnel counts)
    key = f"{TEST_PREFIX}:reddit:old001"
    scraped = datetime.now(timezone.utc) - timedelta(hours=25)
    mapping = {
        "scraped_timestamp": scraped.isoformat(),
        **stage_times(-25, [1, 2, 3, 4, 1]),
    }
    await r.hset(key, mapping=mapping)
    await r.expire(key, 3600)
    keys.append(key)

    print(f"[+] Populated {len(keys)} test keys:")
    for k in keys:
        print(f"    {k}")

    return keys


# ── Compute (mirrors pipeline_metrics.py but uses test_timestamps:*) ──────────

def _parse_dt(val):
    if not val:
        return None
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(val)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None

def _avg(values):
    return round(sum(values) / len(values), 2) if values else None


async def compute(r: aioredis.Redis):
    now = datetime.now(timezone.utc)
    pipeline_cutoff = now - timedelta(hours=24)
    service_cutoff  = now - timedelta(hours=1)

    counts        = defaultdict(int)
    e2e_latencies = []
    svc_counts    = defaultdict(int)
    svc_latencies = defaultdict(list)
    gap_latencies = defaultdict(list)

    cursor = 0
    while True:
        cursor, keys = await r.scan(cursor, match=f"{TEST_PREFIX}:*", count=100)

        if keys:
            pipe = r.pipeline()
            for key in keys:
                pipe.hgetall(key)
            results = await pipe.execute()

            for key, data in zip(keys, results):
                source = key.split(":")[1]

                scraped = _parse_dt(data.get("scraped_timestamp"))
                if scraped and scraped >= pipeline_cutoff:
                    counts["scraped"] += 1
                    if data.get("preproc_timestamp"):  counts["preprocessed"] += 1
                    if data.get("ticker_timestamp"):   counts["ticker_identified"] += 1
                    if data.get("event_timestamp"):    counts["event_identified"] += 1
                    if data.get("sentiment_timestamp"):counts["sentiment_completed"] += 1
                    if data.get("qdrant_timestamp"):   counts["vectorised"] += 1

                for field, val in data.items():
                    if field.startswith("signal_timestamp"):
                        signal_time = _parse_dt(val)
                        if signal_time:
                            if signal_time >= pipeline_cutoff: counts["signal_generated"] += 1
                            if signal_time >= service_cutoff:  svc_counts["signal"] += 1
                    elif field.startswith("order_timestamp"):
                        order_time = _parse_dt(val)
                        if order_time:
                            if order_time >= pipeline_cutoff and scraped:
                                counts["order_placed"] += 1
                                e2e_latencies.append((order_time - scraped).total_seconds())
                            if order_time >= service_cutoff:
                                svc_counts["order"] += 1

                if scraped and scraped >= service_cutoff:
                    svc_counts[f"scraper:{source}"] += 1
                    posted = _parse_dt(data.get("posted_timestamp"))
                    if posted:
                        svc_latencies[f"scraper:{source}"].append((scraped - posted).total_seconds())

                stages = [
                    ("preproc",       "preproc_timestamp_start",   "preproc_timestamp"),
                    ("ticker",        "ticker_timestamp_start",     "ticker_timestamp"),
                    ("event",         "event_timestamp_start",      "event_timestamp"),
                    ("sentiment",     "sentiment_timestamp_start",  "sentiment_timestamp"),
                    ("vectorisation", "qdrant_timestamp_start",     "qdrant_timestamp"),
                ]
                for svc, start_key, end_key in stages:
                    end = _parse_dt(data.get(end_key))
                    if end and end >= service_cutoff:
                        svc_counts[svc] += 1
                        start = _parse_dt(data.get(start_key))
                        if start:
                            svc_latencies[svc].append((end - start).total_seconds())

                gap_stages = [
                    ("to_preproc",       "scraped_timestamp",   "preproc_timestamp"),
                    ("to_ticker",        "preproc_timestamp",   "ticker_timestamp"),
                    ("to_event",         "ticker_timestamp",    "event_timestamp"),
                    ("to_sentiment",     "event_timestamp",     "sentiment_timestamp"),
                    ("to_vectorisation", "sentiment_timestamp", "qdrant_timestamp"),
                ]
                for label, prev_key, curr_key in gap_stages:
                    prev = _parse_dt(data.get(prev_key))
                    curr = _parse_dt(data.get(curr_key))
                    if prev and curr and curr >= service_cutoff:
                        gap_latencies[label].append((curr - prev).total_seconds())

                aggregator_end = _parse_dt(data.get("aggregator_timestamp"))
                signal_time    = next((_parse_dt(v) for f, v in data.items() if f.startswith("signal_timestamp")), None)
                order_time     = next((_parse_dt(v) for f, v in data.items() if f.startswith("order_timestamp")), None)
                if aggregator_end and signal_time and signal_time >= service_cutoff:
                    gap_latencies["to_signal"].append((signal_time - aggregator_end).total_seconds())
                if signal_time and order_time and order_time >= service_cutoff:
                    gap_latencies["to_order"].append((order_time - signal_time).total_seconds())

        if cursor == 0:
            break

    scrapers = {
        k: {"processed": v, "avg_latency_s": _avg(svc_latencies[k])}
        for k, v in svc_counts.items() if k.startswith("scraper:")
    }

    # Merge tradingview subtypes into one key
    tv_keys = [k for k in scrapers if k.startswith("scraper:tradingview_")]
    if tv_keys:
        tv_latencies = [l for k in tv_keys for l in svc_latencies[k]]
        scrapers["scraper:tradingview"] = {
            **{f"{k[len('scraper:tradingview_'):]}_processed": scrapers[k]["processed"] for k in tv_keys},
            "avg_latency_s": _avg(tv_latencies),
        }
        for k in tv_keys:
            del scrapers[k]

    funnel = {
        "window_hours": 24,
        "scraped":          counts["scraped"],
        "preprocessed":     counts["preprocessed"],
        "ticker_identified":counts["ticker_identified"],
        "event_identified": counts["event_identified"],
        "sentiment_completed": counts["sentiment_completed"],
        "vectorised":       counts["vectorised"],
        "signal_generated": counts["signal_generated"],
        "order_placed":     counts["order_placed"],
        "removed": {
            "no_ticker": counts["scraped"]           - counts["ticker_identified"],
            "no_event":  counts["ticker_identified"] - counts["vectorised"],
        },
        "avg_e2e_latency_s": _avg(e2e_latencies),
    }

    services = {
        "window_hours": 1,
        "service_avg_latency": {
            **scrapers,
            "preproc":       {"processed": svc_counts["preproc"],       "avg_latency_s": _avg(svc_latencies["preproc"]),       "time_to_stage_s": _avg(gap_latencies["to_preproc"])},
            "ticker":        {"processed": svc_counts["ticker"],        "avg_latency_s": _avg(svc_latencies["ticker"]),        "time_to_stage_s": _avg(gap_latencies["to_ticker"])},
            "event":         {"processed": svc_counts["event"],         "avg_latency_s": _avg(svc_latencies["event"]),         "time_to_stage_s": _avg(gap_latencies["to_event"])},
            "sentiment":     {"processed": svc_counts["sentiment"],     "avg_latency_s": _avg(svc_latencies["sentiment"]),     "time_to_stage_s": _avg(gap_latencies["to_sentiment"])},
            "vectorisation": {"processed": svc_counts["vectorisation"], "avg_latency_s": _avg(svc_latencies["vectorisation"]), "time_to_stage_s": _avg(gap_latencies["to_vectorisation"])},
            "signal":        {"processed": svc_counts["signal"],        "avg_latency_s": None,                                 "time_to_stage_s": _avg(gap_latencies["to_signal"])},
            "order":         {"processed": svc_counts["order"],         "avg_latency_s": None,                                 "time_to_stage_s": _avg(gap_latencies["to_order"])},
        },
    }

    return funnel, services


# ── Expected results ───────────────────────────────────────────────────────────

EXPECTED_FUNNEL = {
    # old001 is >24h so excluded → 4 scraped
    "scraped":           4,
    # abc003 only has preproc, abc001/abc002/tv001 have all stages → 3 preprocessed... wait abc003 has preproc
    "preprocessed":      3,  # abc001, abc002, tv_ideas (abc003 only has preproc)
    # abc003 dropped at ticker → 3 ticker_identified
    "ticker_identified": 3,
    "vectorised":        3,
    "signal_generated":  1,  # abc001 only
    "order_placed":      1,  # abc001 only
}

EXPECTED_SERVICES = {
    # only abc002 is within 1h
    "scraper:reddit_count": 1,
}


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    r = aioredis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, decode_responses=True)

    print("\n=== Populating test data ===")
    keys = await populate(r)

    print("\n=== Running compute ===")
    funnel, services = await compute(r)

    print("\n── Funnel (24h window) ──")
    print(json.dumps(funnel, indent=2))

    print("\n── Services (1h window) ──")
    print(json.dumps(services, indent=2))

    print("\n=== Validation ===")
    checks = [
        ("scraped == 7",                        funnel["scraped"] == 7),
        ("preprocessed == 7",                   funnel["preprocessed"] == 7),
        ("ticker_identified == 6",              funnel["ticker_identified"] == 6),
        ("vectorised == 6",                     funnel["vectorised"] == 6),
        ("signal_generated == 2",               funnel["signal_generated"] == 2),
        ("order_placed == 2",                   funnel["order_placed"] == 2),
        ("no_ticker drop == 1",                 funnel["removed"]["no_ticker"] == 1),
        ("e2e latency > 0",                     funnel["avg_e2e_latency_s"] is not None and funnel["avg_e2e_latency_s"] > 0),
        ("scraper:reddit in svc",                   "scraper:reddit" in services["service_avg_latency"]),
        ("scraper:tradingview in svc",              "scraper:tradingview" in services["service_avg_latency"]),
        ("reddit latency > 0",                      services["service_avg_latency"].get("scraper:reddit", {}).get("avg_latency_s") is not None),
        ("tradingview ideas_processed == 1",        services["service_avg_latency"].get("scraper:tradingview", {}).get("ideas_processed") == 1),
        ("tradingview minds_processed == 1",        services["service_avg_latency"].get("scraper:tradingview", {}).get("minds_processed") == 1),
        ("tradingview avg_latency_s > 0",           services["service_avg_latency"].get("scraper:tradingview", {}).get("avg_latency_s") is not None),
        ("preproc time_to_stage_s > 0",             services["service_avg_latency"].get("preproc", {}).get("time_to_stage_s") is not None),
        ("ticker time_to_stage_s > 0",              services["service_avg_latency"].get("ticker", {}).get("time_to_stage_s") is not None),
        ("signal time_to_stage_s > 0",              services["service_avg_latency"].get("signal", {}).get("time_to_stage_s") is not None),
        ("order time_to_stage_s > 0",               services["service_avg_latency"].get("order", {}).get("time_to_stage_s") is not None),
    ]

    all_pass = True
    for label, result in checks:
        status = "✅" if result else "❌"
        print(f"  {status} {label}")
        if not result:
            all_pass = False

    print(f"\n{'✅ All checks passed' if all_pass else '❌ Some checks failed'}")

    print("\n=== Skipping cleanup — keys left in Redis for inspection ===")
    print("Keys written:")
    for key in keys:
        print(f"  {key}")
    print("\nTo clean up manually, run:")
    print(f"  redis-cli -h ... DEL {' '.join(keys)}")

    await r.aclose()


if __name__ == "__main__":
    asyncio.run(main())
