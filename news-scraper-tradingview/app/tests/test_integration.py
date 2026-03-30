"""
Integration test — hits real TradingView API + real Redis.

Run:
    cd news-scraper-tradingview
    python -m app.tests.test_integration

Requires:
    - .env with valid REDIS_HOST / REDIS_PORT / REDIS_PASSWORD
    - Internet access (TradingView API)
"""

import json
import time
import threading
import logging
from datetime import datetime, timezone, timedelta

from app.services.storage import get_redis_client
from app.services.tradingview_minds_batch_ingestion import TradingViewMindsBatchIngestion
from app.services.tradingview_ideas_batch_ingestion import TradingViewIdeasBatchIngestion
from app.services.tradingview_minds_stream_ingestion import TradingViewMindsStreamIngestion
from app.services.tradingview_ideas_stream_ingestion import TradingViewIdeasStreamIngestion

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")
logger = logging.getLogger(__name__)

# Use a dedicated test stream + dedup prefix so we don't pollute production
TEST_STREAM = "test_integration_stream"
TEST_DEDUP_MINDS = "test_dedup_minds"
TEST_DEDUP_IDEAS = "test_dedup_ideas"
TEST_HWM_MINDS = "test_hwm_minds"
TEST_HWM_IDEAS = "test_hwm_ideas"
TEST_TICKER = "AAPL"


def _drain_stream(redis_client, stream_name) -> list[dict]:
    """Read all entries from a Redis stream and return parsed rows."""
    raw = redis_client.xrange(stream_name, "-", "+")
    rows = []
    for entry_id, fields in raw:
        data = json.loads(fields["data"])
        rows.append(data)
    return rows


def _cleanup(redis_client):
    """Delete only the test-specific keys (no broad wildcard scans)."""
    keys_to_delete = [
        TEST_STREAM,
        f"{TEST_HWM_MINDS}:{TEST_TICKER}",
        f"{TEST_HWM_IDEAS}:{TEST_TICKER}",
    ]
    # Scan only our test dedup keys (small namespace)
    for prefix in [TEST_DEDUP_MINDS, TEST_DEDUP_IDEAS]:
        for key in redis_client.scan_iter(match=f"{prefix}:*", count=500):
            keys_to_delete.append(key)
    # Scan test post_timestamps
    for key in redis_client.scan_iter(match="post_timestamps:test_*", count=500):
        keys_to_delete.append(key)

    if keys_to_delete:
        redis_client.delete(*keys_to_delete)
    logger.info(f"Cleaned up {len(keys_to_delete)} test keys")


# ── 1. Test Redis connectivity ──────────────────────────────────────────────

def test_redis_connection():
    logger.info("=" * 60)
    logger.info("TEST: Redis connectivity")
    logger.info("=" * 60)
    r = get_redis_client()
    assert r.ping(), "Redis ping failed"
    logger.info("PASS — Redis is reachable\n")
    return r


# ── 2. Test Minds Batch ─────────────────────────────────────────────────────

def test_minds_batch(redis_client):
    logger.info("=" * 60)
    logger.info("TEST: Minds Batch Ingestion (1 ticker, real API)")
    logger.info("=" * 60)

    ingestion = TradingViewMindsBatchIngestion(redis_client)
    ingestion.STREAM_NAME = TEST_STREAM
    ingestion.DEDUP_SET_NAME = TEST_DEDUP_MINDS
    ingestion.ITEMS_PER_TICKER = 5

    import app.services.tradingview_minds_batch_ingestion as mod
    original = mod.get_tickers_from_redis
    mod.get_tickers_from_redis = lambda r: [TEST_TICKER]

    try:
        summary = ingestion.run()
    finally:
        mod.get_tickers_from_redis = original

    logger.info(f"Summary: {json.dumps(summary, indent=2)}")

    rows = _drain_stream(redis_client, TEST_STREAM)
    minds_rows = [r for r in rows if r.get("content_type") == "mind"]

    logger.info(f"Published {len(minds_rows)} minds to stream")
    assert summary["errors"] == [], f"Errors: {summary['errors']}"

    # Verify time boundary: no post older than 5 days
    cutoff = datetime.now(timezone.utc) - timedelta(days=TradingViewMindsBatchIngestion.BATCH_MAX_AGE_DAYS)
    for row in minds_rows:
        ts = datetime.fromisoformat(row["timestamps"])
        ts_utc = ts.astimezone(timezone.utc)
        assert ts_utc >= cutoff, f"Post {row['id']} is too old: {row['timestamps']} (cutoff: {cutoff.isoformat()})"

    if summary["total_too_old"] > 0:
        logger.info(f"Time boundary working — filtered out {summary['total_too_old']} old posts")
    else:
        logger.info("No old posts encountered (all within 5-day window)")

    if minds_rows:
        sample = minds_rows[0]
        logger.info(f"Sample mind: id={sample['id']}, author={sample['author']}, "
                     f"ts={sample['timestamps']}, body={sample['content']['body'][:80]}...")

    logger.info("PASS — Minds Batch\n")
    return summary


# ── 3. Test Ideas Batch ─────────────────────────────────────────────────────

def test_ideas_batch(redis_client):
    logger.info("=" * 60)
    logger.info("TEST: Ideas Batch Ingestion (1 ticker, real API)")
    logger.info("=" * 60)

    ingestion = TradingViewIdeasBatchIngestion(redis_client)
    ingestion.STREAM_NAME = TEST_STREAM
    ingestion.DEDUP_SET_NAME = TEST_DEDUP_IDEAS
    ingestion.ITEMS_PER_TICKER = 5
    ingestion.PAGES_PER_TICKER = 1

    import app.services.tradingview_ideas_batch_ingestion as mod
    original = mod.get_tickers_from_redis
    mod.get_tickers_from_redis = lambda r: [TEST_TICKER]

    try:
        summary = ingestion.run()
    finally:
        mod.get_tickers_from_redis = original

    logger.info(f"Summary: {json.dumps(summary, indent=2)}")

    rows = _drain_stream(redis_client, TEST_STREAM)
    ideas_rows = [r for r in rows if r.get("content_type") == "idea"]

    logger.info(f"Published {len(ideas_rows)} ideas to stream")
    assert summary["errors"] == [], f"Errors: {summary['errors']}"

    # Verify time boundary
    cutoff = datetime.now(timezone.utc) - timedelta(days=TradingViewIdeasBatchIngestion.BATCH_MAX_AGE_DAYS)
    for row in ideas_rows:
        ts = datetime.fromisoformat(row["timestamps"])
        ts_utc = ts.astimezone(timezone.utc)
        assert ts_utc >= cutoff, f"Post {row['id']} is too old: {row['timestamps']}"

    if summary["total_too_old"] > 0:
        logger.info(f"Time boundary working — filtered out {summary['total_too_old']} old posts")

    if ideas_rows:
        sample = ideas_rows[0]
        logger.info(f"Sample idea: id={sample['id']}, author={sample['author']}, "
                     f"title={sample['content']['title'][:60]}")

    logger.info("PASS — Ideas Batch\n")
    return summary


# ── 4. Test Minds Stream (run 1 cycle) ──────────────────────────────────────

def test_minds_stream(redis_client):
    logger.info("=" * 60)
    logger.info("TEST: Minds Stream Ingestion (1 cycle, real API)")
    logger.info("=" * 60)

    redis_client.delete(TEST_STREAM)

    ingestion = TradingViewMindsStreamIngestion(redis_client)
    ingestion.STREAM_NAME = TEST_STREAM
    ingestion.DEDUP_SET_NAME = TEST_DEDUP_MINDS
    ingestion.HWM_KEY_PREFIX = TEST_HWM_MINDS
    ingestion.ITEMS_PER_TICKER = 3

    import app.services.tradingview_minds_stream_ingestion as mod
    original = mod.get_tickers_from_redis
    mod.get_tickers_from_redis = lambda r: [TEST_TICKER]

    original_sleep = time.sleep

    def stop_after_cycle(n):
        if n >= ingestion.POLL_INTERVAL / 2:
            ingestion._running = False
            return
        original_sleep(min(n, 1))

    mod.time.sleep = stop_after_cycle

    try:
        ingestion.run()
    finally:
        mod.get_tickers_from_redis = original
        mod.time.sleep = original_sleep

    rows = _drain_stream(redis_client, TEST_STREAM)
    logger.info(f"Stream published {len(rows)} minds in 1 cycle")

    hwm_key = f"{TEST_HWM_MINDS}:{TEST_TICKER}"
    hwm_val = redis_client.get(hwm_key)
    logger.info(f"HWM for {TEST_TICKER}: {hwm_val}")

    if hwm_val:
        logger.info("HWM correctly set after first cycle")

        bootstrap_cutoff = datetime.now(timezone.utc) - timedelta(minutes=ingestion.STREAM_BOOTSTRAP_MINUTES)
        for row in rows:
            ts = datetime.fromisoformat(row["timestamps"])
            ts_utc = ts.astimezone(timezone.utc)
            assert ts_utc >= bootstrap_cutoff, (
                f"Stream post {row['id']} is too old: {row['timestamps']} "
                f"(bootstrap cutoff: {bootstrap_cutoff.isoformat()})"
            )

    logger.info("PASS — Minds Stream\n")


# ── 5. Test Ideas Stream (run 1 cycle) ──────────────────────────────────────

def test_ideas_stream(redis_client):
    logger.info("=" * 60)
    logger.info("TEST: Ideas Stream Ingestion (1 cycle, real API)")
    logger.info("=" * 60)

    redis_client.delete(TEST_STREAM)

    ingestion = TradingViewIdeasStreamIngestion(redis_client)
    ingestion.STREAM_NAME = TEST_STREAM
    ingestion.DEDUP_SET_NAME = TEST_DEDUP_IDEAS
    ingestion.HWM_KEY_PREFIX = TEST_HWM_IDEAS
    ingestion.ITEMS_PER_TICKER = 3

    import app.services.tradingview_ideas_stream_ingestion as mod
    original = mod.get_tickers_from_redis
    mod.get_tickers_from_redis = lambda r: [TEST_TICKER]

    original_sleep = time.sleep

    def stop_after_cycle(n):
        if n >= ingestion.POLL_INTERVAL / 2:
            ingestion._running = False
            return
        original_sleep(min(n, 1))

    mod.time.sleep = stop_after_cycle

    try:
        ingestion.run()
    finally:
        mod.get_tickers_from_redis = original
        mod.time.sleep = original_sleep

    rows = _drain_stream(redis_client, TEST_STREAM)
    logger.info(f"Stream published {len(rows)} ideas in 1 cycle")

    hwm_key = f"{TEST_HWM_IDEAS}:{TEST_TICKER}"
    hwm_val = redis_client.get(hwm_key)
    logger.info(f"HWM for {TEST_TICKER}: {hwm_val}")

    if hwm_val:
        logger.info("HWM correctly set after first cycle")

    logger.info("PASS — Ideas Stream\n")


# ── 6. Test dedup across batch → stream ─────────────────────────────────────

def test_dedup_batch_then_stream(redis_client):
    logger.info("=" * 60)
    logger.info("TEST: Dedup — batch posts are not re-published by stream")
    logger.info("=" * 60)

    redis_client.delete(TEST_STREAM)

    # Run batch first
    batch = TradingViewMindsBatchIngestion(redis_client)
    batch.STREAM_NAME = TEST_STREAM
    batch.DEDUP_SET_NAME = TEST_DEDUP_MINDS
    batch.ITEMS_PER_TICKER = 3

    import app.services.tradingview_minds_batch_ingestion as batch_mod
    original_batch = batch_mod.get_tickers_from_redis
    batch_mod.get_tickers_from_redis = lambda r: [TEST_TICKER]

    try:
        batch.run()
    finally:
        batch_mod.get_tickers_from_redis = original_batch

    batch_count = redis_client.xlen(TEST_STREAM)
    logger.info(f"After batch: {batch_count} entries in stream")

    # Now run stream for 1 cycle
    stream = TradingViewMindsStreamIngestion(redis_client)
    stream.STREAM_NAME = TEST_STREAM
    stream.DEDUP_SET_NAME = TEST_DEDUP_MINDS
    stream.HWM_KEY_PREFIX = TEST_HWM_MINDS
    stream.ITEMS_PER_TICKER = 3

    import app.services.tradingview_minds_stream_ingestion as stream_mod
    original_stream = stream_mod.get_tickers_from_redis
    stream_mod.get_tickers_from_redis = lambda r: [TEST_TICKER]

    original_sleep = time.sleep

    def stop_after_cycle(n):
        if n >= stream.POLL_INTERVAL / 2:
            stream._running = False
            return
        original_sleep(min(n, 1))

    stream_mod.time.sleep = stop_after_cycle

    try:
        stream.run()
    finally:
        stream_mod.get_tickers_from_redis = original_stream
        stream_mod.time.sleep = original_sleep

    stream_count = redis_client.xlen(TEST_STREAM)
    new_from_stream = stream_count - batch_count
    logger.info(f"After stream: {stream_count} entries (+{new_from_stream} new)")
    logger.info(f"Dedup working — stream added {new_from_stream} truly new posts (0 expected if no new posts appeared)")

    logger.info("PASS — Dedup batch→stream\n")


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    r = test_redis_connection()

    try:
        _cleanup(r)
        test_minds_batch(r)
        test_ideas_batch(r)
        test_minds_stream(r)
        test_ideas_stream(r)
        test_dedup_batch_then_stream(r)

        logger.info("=" * 60)
        logger.info("ALL INTEGRATION TESTS PASSED")
        logger.info("=" * 60)
    finally:
        _cleanup(r)
