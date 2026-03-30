import asyncio
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import boto3
from redis.asyncio import Redis

from app.core.config import env_config

s3_client = boto3.client(
    "s3",
    aws_access_key_id=env_config.aws_access_key_id,
    aws_secret_access_key=env_config.aws_secret_access_key,
    region_name=env_config.aws_region,
)

redis_client = Redis(
    host=env_config.redis_host,
    port=env_config.redis_port,
    password=env_config.redis_password,
    decode_responses=True,
)

FUNNEL_SNAPSHOT_KEY   = "metrics:pipeline:funnel"
SERVICE_SNAPSHOT_KEY  = "metrics:pipeline:services"
PIPELINE_WINDOW_HOURS = 24  # pipeline funnel: 1 day
SERVICE_WINDOW_HOURS  = 1   # per-service metrics: 1 hour


def _parse_dt(val: str) -> datetime | None:
    if not val:
        return None
    try:
        dt = datetime.fromisoformat(val)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _avg(values: list) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


async def compute_pipeline_metrics():
    now = datetime.now(ZoneInfo("Asia/Singapore"))
    pipeline_cutoff = now - timedelta(hours=PIPELINE_WINDOW_HOURS)
    service_cutoff  = now - timedelta(hours=SERVICE_WINDOW_HOURS)

    counts        = defaultdict(int)
    e2e_latencies = []
    svc_counts    = defaultdict(int)
    svc_latencies = defaultdict(list)
    gap_latencies = defaultdict(list)  # prev_end → curr_end (queue + processing per stage)

    cursor = 0
    while True:
        cursor, keys = await redis_client.scan(cursor, match="post_timestamps:*", count=100)

        if keys:
            pipe = redis_client.pipeline()
            for key in keys:
                pipe.hgetall(key)
            results = await pipe.execute()

            for key, data in zip(keys, results):
                # Extract source from key: post_timestamps:{source}:{post_id}
                source = key.split(":")[1]  # e.g. "reddit", "tradingview_ideas", "tradingview_minds"

                # ── Pipeline funnel (24h window on scraped_timestamp) ──────
                scraped = _parse_dt(data.get("scraped_timestamp"))
                if scraped and scraped >= pipeline_cutoff:
                    counts["scraped"] += 1
                    if data.get("preproc_timestamp"):
                        counts["preprocessed"] += 1
                    if data.get("ticker_timestamp"):
                        counts["ticker_identified"] += 1
                    if data.get("event_timestamp"):
                        counts["event_identified"] += 1
                    if data.get("sentiment_timestamp"):
                        counts["sentiment_completed"] += 1
                    if data.get("qdrant_timestamp"):
                        counts["vectorised"] += 1

                for field, val in data.items():
                    if field.startswith("signal_timestamp"):
                        signal_time = _parse_dt(val)
                        if signal_time:
                            if signal_time >= pipeline_cutoff:
                                counts["signal_generated"] += 1
                            if signal_time >= service_cutoff:
                                svc_counts["signal"] += 1

                    elif field.startswith("order_timestamp"):
                        order_time = _parse_dt(val)
                        if order_time:
                            if order_time >= pipeline_cutoff and scraped:
                                counts["order_placed"] += 1
                                e2e_latencies.append((order_time - scraped).total_seconds())
                            if order_time >= service_cutoff:
                                svc_counts["order"] += 1

                # ── Per-service metrics (1h window on each end timestamp) ──

                # Scrapers — count by source, latency = scraped_timestamp - posted_timestamp
                if scraped and scraped >= service_cutoff:
                    svc_counts[f"scraper:{source}"] += 1
                    posted = _parse_dt(data.get("posted_timestamp"))
                    if posted:
                        svc_latencies[f"scraper:{source}"].append((scraped - posted).total_seconds())

                # Pipeline services
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

                # gap_latencies: prev_end → curr_end
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

    # Build scraper entries dynamically from whatever sources exist
    scrapers = {
        k: {"processed": v, "avg_latency_s": _avg(svc_latencies[k])}
        for k, v in svc_counts.items()
        if k.startswith("scraper:")
    }

    # Merge tradingview subtypes into one key
    tv_keys = [k for k in scrapers if k.startswith("scraper:tradingview_")]
    if tv_keys:
        tv_latencies = [l for k in tv_keys for l in svc_latencies[k]]
        scrapers["scraper:tradingview"] = {
            "minds_processed": scrapers.get("scraper:tradingview_minds", {}).get("processed", 0),
            "ideas_processed": scrapers.get("scraper:tradingview_ideas", {}).get("processed", 0),
            "avg_latency_s":   _avg(tv_latencies),
        }
        for k in tv_keys:
            del scrapers[k]

    # Always include reddit and tradingview with defaults if missing
    scrapers.setdefault("scraper:reddit",      {"processed": 0, "avg_latency_s": None})
    scrapers.setdefault("scraper:tradingview", {"minds_processed": 0, "ideas_processed": 0, "avg_latency_s": None})

    funnel_snapshot = {
        "computed_at":      now.isoformat(),
        "window_hours":     PIPELINE_WINDOW_HOURS,
        "scraped":          counts["scraped"],
        "vectorised":       counts["vectorised"],
        "signal_generated": counts["signal_generated"],
        "order_placed":     counts["order_placed"],
        "removed": {
            "no_ticker": counts["scraped"]           - counts["ticker_identified"],
            "no_event":  counts["ticker_identified"] - counts["vectorised"],
        },
        "avg_e2e_latency_s": _avg(e2e_latencies),
    }

    services_snapshot = {
        "computed_at":  now.isoformat(),
        "window_hours": SERVICE_WINDOW_HOURS,
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

    print("[funnel]", funnel_snapshot)
    print("[services]", services_snapshot)

    pipe = redis_client.pipeline()
    pipe.set(FUNNEL_SNAPSHOT_KEY,  json.dumps(funnel_snapshot))
    pipe.set(SERVICE_SNAPSHOT_KEY, json.dumps(services_snapshot))
    await pipe.execute()

    # Archive to S3 once per hour — overwrites the daily file, 24 writes/day
    if now.minute < 5:
        try:
            date_str = now.strftime("%Y-%m-%d")
            s3_client.put_object(
                Bucket=env_config.aws_bucket_name,
                Key=f"metrics/pipeline/{date_str}.json",
                Body=json.dumps(funnel_snapshot),
                ContentType="application/json",
            )
            print(f"[pipeline_metrics] Archived snapshot to S3: metrics/pipeline/{date_str}.json")
        except Exception as e:
            print(f"[pipeline_metrics] S3 archive failed (non-fatal): {e}")


async def run_aggregator():
    while True:
        try:
            await compute_pipeline_metrics()
        except Exception as e:
            print(f"[pipeline_metrics] aggregator error: {e}")
        await asyncio.sleep(900)  # every 15 mins


if __name__ == "__main__":
    asyncio.run(compute_pipeline_metrics())
